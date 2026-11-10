"""S55J: scoring of the remaining-260 predictions under the frozen metric/adapter and the S55F-style Community protocol,
generalised to four graphs. Modes: offline-check | community-preflight | score. The live modes need separate owner authorization.
No metric change; the frozen project_ex / score_predictions bytes are reused. Query execution happens only in `score`."""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import argparse, csv, hashlib, json, os, sys, zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent; TRACK = HERE.parent
sys.path.insert(0, str(TRACK / "kaggle"))
import ext260_notebook_support as ext
import community_isolation_55j as iso
import score_predictions as sp
from project_ex import VERSION
from gate40_workflow_55d import METRIC_SHA, ADAPTER_SHA

PACKET = TRACK / "data/packet_mtq_remaining260.jsonl"; PACKET_SHA = ext.HASHES["data/packet_mtq_remaining260.jsonl"]
MAPPING = TRACK / "GATE260_FOUR_GRAPH_MAPPING.json"; MAPPING_SHA = "41e5fa12e641cbcb66cc772c02e118b0295447a10f33ea973bc34fdb026abd6b"
ROUTES = {"bloom": "s55bloom", "er": "s55er", "healthcare": "s55health", "wwc": "s55wwc"}
MODELS = ("qwen", "mistral")

def validate_archive(zip_path):
    """Returned ext260 archive: safe ZIP, SHA256SUMS match, manifest complete, per-model validated rows. Returns {model: rows}."""
    with zipfile.ZipFile(zip_path) as z:
        if z.testzip() is not None: raise ValueError("ZIP CRC")
        names = z.namelist()
        if len(names) != len(set(names)) or any(n.startswith("/") or ".." in Path(n).parts for n in names): raise ValueError("unsafe ZIP")
        sums = dict(l.split("  ", 1)[::-1] for l in z.read("SHA256SUMS").decode().splitlines())
        for n, h in sums.items():
            if hashlib.sha256(z.read(n)).hexdigest() != h: raise ValueError("member hash mismatch: " + n)
        man = json.loads(z.read("execution_manifest.json"))
        if man.get("phase") != "ext260" or man.get("complete") is not True or man.get("errors"): raise ValueError("archive not complete ext260 evidence")
        out = {}
        for m in MODELS:
            name = "s55_%s_mtq_ext260.jsonl" % m
            if name not in sums: raise ValueError("missing predictions " + name)
            out[m] = [json.loads(l) for l in z.read(name).decode().splitlines()]
    ids = [json.loads(l)["question_id"] for l in PACKET.read_text().splitlines()]
    import tempfile
    for m, rows in out.items():
        if [r["question_id"] for r in rows] != ids: raise ValueError("ID coverage/order: " + m)
        with tempfile.TemporaryDirectory(dir=TRACK / "runtime_55j" if (TRACK / "runtime_55j").exists() else None) as d:   # full row validation, same code as the notebook
            f = Path(d) / "rows.jsonl"; f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
            ext.validate_output(f, m, ids, PACKET_SHA, ext.HASHES["kaggle/prompt_template.txt"], TRACK / "kaggle/run_inference.py")
    return out, man

def inputs(mtq_source, dump_root, predictions):
    if sp.sha(PACKET) != PACKET_SHA or sp.sha(MAPPING) != MAPPING_SHA: raise ValueError("packet/mapping drift")
    if sp.sha(HERE / "project_ex.py") != METRIC_SHA or sp.sha(HERE / "score_predictions.py") != ADAPTER_SHA: raise ValueError("frozen metric/adapter drift")
    mapping = json.loads(MAPPING.read_text()); packet = [json.loads(l) for l in PACKET.read_text().splitlines()]
    if set(mapping["graphs"]) != set(iso.GRAPH_IDS) or {g: v["database"] for g, v in mapping["graphs"].items()} != ROUTES: raise ValueError("route drift")
    for g, v in mapping["graphs"].items():
        if sp.sha(Path(dump_root) / v["dump_file"]) != v["dump_sha256"]: raise ValueError("dump hash drift " + g)
        if v["question_ids"] != [r["question_id"] for r in packet if r["graph"] == g]: raise ValueError("graph membership drift " + g)
    refs = sp.reference_map(mtq_source, packet)
    if any(refs[r["question_id"]][0] != r["graph"] for r in packet): raise ValueError("reference graph mismatch")
    preds, man = validate_archive(predictions) if predictions else ({}, None)
    return packet, preds, refs, mapping, man

def summarize(traces):
    """Fixed 260 denominator per model; per-graph and status breakdown; no continuation gate here (floor already applied at Gate40)."""
    out = {}
    for m in MODELS:
        rows = [t for t in traces if t["model"] == m]
        if len(rows) != 260 or len({t["question_id"] for t in rows}) != 260: raise ValueError("incomplete/duplicate verdicts")
        out[m] = {"correct": sum(t["status"] == "scored" and t["verdict"] == 1 for t in rows), "denominator": 260,
                  "status_counts": dict(sorted(Counter(t["status"] for t in rows).items())),
                  "invalid_reference_or_unsupported": sum(t["status"] in ("invalid_reference", "unsupported") for t in rows)}
    return out

def main():
    import workflow_lib_55j as lib
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument("mode", choices=("offline-check", "community-preflight", "score"))
    ap.add_argument("--mtq-source", type=Path, required=True); ap.add_argument("--dump-root", type=Path, required=True)
    ap.add_argument("--predictions", type=Path, help="returned ext260 archive ZIP"); ap.add_argument("--output-dir", type=Path)
    ap.add_argument("--owner-authorized-live", action="store_true"); a = ap.parse_args()
    iso.validate_endpoints()
    packet, preds, refs, mapping, man = inputs(a.mtq_source, a.dump_root, a.predictions if a.mode != "community-preflight" else None)
    if a.mode == "offline-check":
        print(json.dumps({"status": "OFFLINE_PASS", "scored": False, "graphs": {g: v["question_count"] for g, v in mapping["graphs"].items()}, "predictions_validated": bool(preds)})); return
    if not (a.owner_authorized_live and a.output_dir): raise SystemExit("live mode requires separate owner authorization and a new output directory")
    if a.mode == "score" and not a.predictions: raise SystemExit("--predictions required")
    if a.output_dir.exists() or a.output_dir.with_suffix(".zip").exists(): raise SystemExit("output exists; preserve prior evidence")
    from neo4j.exceptions import Neo4jError
    drivers = lib.connect()
    try:
        report, before = lib.preflight(drivers, mapping, test_denial=True, neo4j_error=Neo4jError)
        if a.mode == "community-preflight":
            a.output_dir.mkdir(parents=True); (a.output_dir / "preflight.json").write_text(json.dumps(report, indent=2) + "\n"); return
        traces, project_rows, after = lib.run_scoring(packet, preds, refs, drivers, ROUTES, before)
    finally:
        for d in drivers.values(): d.close()
    if len(traces) != 520: raise ValueError("incomplete scoring trace")
    summary = summarize(traces)
    sp.write_outputs(traces, sp.analysis_rows(traces, project_rows, {}), a.output_dir)
    (a.output_dir / "execution_manifest.json").write_text(json.dumps({"phase": "ext260 native graph scoring (Community, four containers)", "metric": VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(), "packet_sha256": PACKET_SHA, "mapping_sha256": MAPPING_SHA, "evaluator_sha256": METRIC_SHA,
        "adapter_sha256": ADAPTER_SHA, "workflow_sha256": sp.sha(Path(__file__)), "predictions_archive_sha256": sp.sha(a.predictions),
        "preflight": report, "stable_snapshot_after": after, "summary": summary, "trace_count": len(traces), "scored": True}, indent=2) + "\n")
    (a.output_dir / "SHA256SUMS").write_text("".join("%s  %s\n" % (sp.sha(a.output_dir / n), n) for n in ("execution_traces.jsonl", "scorer_verdicts.csv", "execution_manifest.json")))
    print(json.dumps({"status": "SCORED", "summary": summary}))

if __name__ == "__main__": main()
