#!/usr/bin/env python3
"""End-to-end reproduction driver for the model-output case study (paper Section VII, Table IX), release 1.3.0.

Stages (run from the artifact root; each stage checks the previous one's outputs):
  prepare  verify the Mind the Query checkout (pinned commit), rebuild the three frozen question packets from the
           released question IDs and compare their SHA-256 with the frozen values, verify prediction and dump hashes.
           Offline once Mind the Query has been fetched.
  execute  [Docker] provision four read-only Neo4j 5.15.0 Community containers (one per graph), run the live
           security/identity preflight, execute every gold and predicted query with the frozen baseline comparator
           (project_ex.py, unchanged) for Gate40 and the 260-question extension, check graph integrity before/after.
  replay   run the nine pinned comparators (fetched with third_party/fetch_scorers.sh) unchanged on the recorded
           result pairs (network blocked inside the runner).
  table    rebuild the 600-unit verdict table from the new traces and verdicts, compare it byte-for-byte with
           verdicts/case_study_units.csv, and recompute Table IX (code/recompute_case_study.py).

Usage:  python3 studies/model_output_case_study/code/reproduce_case_study.py STAGE [--work DIR] [--mtq external/mind_the_query]
The frozen comparator, adapters and scorer code are never modified. The execute stage needs Docker and about 4 GB RAM.
"""
import argparse, csv, hashlib, json, os, runpy, subprocess, sys
from pathlib import Path

CS = Path(__file__).resolve().parents[1]           # studies/model_output_case_study
ART = CS.parents[1]                                  # artifact root
sys.path.insert(0, str(CS / "code"))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
EXP = json.loads((CS / "frozen/expected_input_hashes.json").read_text())
ROUTES = {"bloom": "s55bloom", "er": "s55er", "healthcare": "s55health", "wwc": "s55wwc"}
SCHEMA_KEY = {"bloom": "bloom50", "covid": "covid", "er": "er", "healthcare": "healthcare", "wwc": "wwc"}


def die(msg):
    raise SystemExit("STOP: " + msg)


def jsonl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines()]


def prepare(a):
    mtq = Path(a.mtq).resolve()
    rev = subprocess.run(["git", "-C", str(mtq), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if rev != EXP["mtq_commit"]:
        die("Mind the Query checkout %s is not at the pinned commit %s (run third_party/fetch_mind_the_query.sh)" % (rev or "missing", EXP["mtq_commit"]))
    found = {}
    for f in sorted((mtq / "Train_Test_Splits/Manual").glob("*/test/*.json")):
        graph = f.relative_to(mtq / "Train_Test_Splits/Manual").parts[0]
        for r in json.loads(f.read_text()):
            found.setdefault(r["unique_id"], (graph, r))
    schema = {}
    for line in (mtq / "db_schema.jsonl").open():
        schema.update(json.loads(line))
    work = Path(a.work); (work / "packets").mkdir(parents=True, exist_ok=True)
    for name in ("300", "gate40", "remaining260"):
        ids = json.loads((CS / ("frozen/question_ids_%s.json" % name)).read_text())
        out = work / ("packets/packet_mtq_%s.jsonl" % name)
        with out.open("w") as fh:
            for x in ids:
                g, r = found[x["question_id"]]
                if g != x["graph"]:
                    die("graph mismatch for " + x["question_id"])
                rec = {"question_id": r["unique_id"], "benchmark": "mind_the_query", "graph": g, "question": r["NL Question"], "schema": schema[SCHEMA_KEY[g]]}
                fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
        if sha(out) != EXP["packets"]["packet_mtq_%s.jsonl" % name]:
            die("rebuilt packet %s differs from the frozen packet" % name)
    for n, h in EXP["predictions"].items():
        if sha(CS / "predictions" / n) != h:
            die("prediction file hash drift: " + n)
    mapping = json.loads((CS / "GATE260_FOUR_GRAPH_MAPPING.json").read_text())
    for g, v in mapping["graphs"].items():
        if sha(mtq / "Datasets" / v["dump_file"]) != v["dump_sha256"]:
            die("dump hash mismatch: " + g)
    print(json.dumps({"stage": "prepare", "status": "PASS", "mtq_commit": rev, "packets_rebuilt_identical": 3, "predictions_verified": 4, "dumps_verified": 4}))


def _image():
    """Portable image check: the frozen run used the arm64 image ID of neo4j:5.15.0 Community; other architectures
    have other IDs. We require the official tag, Community edition and the 5.15.0 tarball, and record the ID used."""
    out = None
    refs = ["neo4j:5.15.0", "docker.io/library/neo4j:5.15.0"]
    listed = subprocess.run(["docker", "images", "-q", "neo4j:5.15.0"], capture_output=True, text=True).stdout.split()
    for ref in refs + listed[:1]:                     # some Docker image stores resolve only the ID or the full name
        out = subprocess.run(["docker", "image", "inspect", ref], capture_output=True, text=True)
        if out.returncode == 0:
            break
    if out is None or out.returncode:
        die("image neo4j:5.15.0 not present; run: docker pull neo4j:5.15.0")
    it = json.loads(out.stdout)[0]
    env = dict(x.split("=", 1) for x in it["Config"]["Env"] if "=" in x)
    if env.get("NEO4J_EDITION") != "community" or env.get("NEO4J_TARBALL") != "neo4j-community-5.15.0-unix.tar.gz":
        die("neo4j:5.15.0 is not the Community 5.15.0 image")
    return {"image_id": it["Id"], "architecture": it["Architecture"], "edition": env["NEO4J_EDITION"], "tarball": env["NEO4J_TARBALL"]}


def execute(a):
    import community_isolation_55j as iso, provision_community_55j as prov, workflow_lib_55j as lib
    import score_predictions as sp
    from project_ex import VERSION
    work = Path(a.work)
    if not (work / "packets/packet_mtq_gate40.jsonl").exists():
        die("run the prepare stage first")
    img = _image()
    iso.IMAGE_ID = img["image_id"]                    # used by run_argv/load_argv
    if a.container_prefix or a.port_base:             # avoid clashing with existing containers; never reuse or delete them
        for i, g in enumerate(sorted(iso.ENDPOINTS)):
            e = iso.ENDPOINTS[g]
            if a.container_prefix:
                e["container"] = a.container_prefix + e["container"].split("-")[-1]
            if a.port_base:
                e["port"] = a.port_base + i
        iso.validate_endpoints()
    prov.image_preflight = lambda: img                 # portable check above replaces the arm64-ID check
    mapping = prov.build_plan(Path(a.mtq) / "Datasets")
    if not a.reuse_running:
        prov.execute(mapping, Path(a.mtq) / "Datasets", deployment_ok=True, amendment_ok=True)
    from neo4j.exceptions import Neo4jError
    drivers = lib.connect()
    stages = {}
    try:
        report, before = lib.preflight(drivers, mapping, test_denial=True, neo4j_error=Neo4jError)
        for stage, model_files in (("gate40", ("s55_qwen_mtq_gate40.jsonl", "s55_mistral_mtq_gate40.jsonl")),
                                   ("ext260", ("s55_qwen_mtq_ext260.jsonl", "s55_mistral_mtq_ext260.jsonl"))):
            packet = jsonl(work / ("packets/packet_mtq_%s.jsonl" % ("gate40" if stage == "gate40" else "remaining260")))
            preds = {"qwen": jsonl(CS / "predictions" / model_files[0]), "mistral": jsonl(CS / "predictions" / model_files[1])}
            refs = sp.reference_map(Path(a.mtq), packet)
            traces, rows, after = lib.run_scoring(packet, preds, refs, drivers, ROUTES, before)
            out = work / ("execution_" + stage)
            sp.write_outputs(traces, sp.analysis_rows(traces, rows, {}), out)
            stages[stage] = {"units": len(traces), "integrity_after": after}
    finally:
        for d in drivers.values():
            d.close()
    (work / "execute_manifest.json").write_text(json.dumps({"metric": VERSION, "image": img, "preflight": report, "stages": stages}, indent=1, default=str))
    print(json.dumps({"stage": "execute", "status": "PASS", "units": {k: v["units"] for k, v in stages.items()}, "image": img}))


def replay(a):
    import score_predictions as sp
    sp.ADAPTER = ART / "studies/adapter_readiness/audit_readiness/code/audit_adapters.py"   # the frozen adapter, inside this artifact
    work = Path(a.work)
    for stage in ("gate40", "ext260"):
        src = work / ("execution_" + stage)
        if not (src / "execution_traces.jsonl").exists():
            die("run the execute stage first (missing %s)" % src)
        out = work / ("replay_" + stage)
        if out.exists():
            die("%s exists; use a new --work directory" % out)
        argv = sys.argv
        sys.argv = ["run_scorer_impact_55h.py", str(src), str(ART), str(out)]
        try:
            runpy.run_path(str(CS / "code/run_scorer_impact_55h.py"), run_name="__main__")
        finally:
            sys.argv = argv
    print(json.dumps({"stage": "replay", "status": "PASS"}))


def table(a):
    work = Path(a.work)
    flags = {r["question_id"]: r for r in csv.DictReader((CS / "frozen/near_overlap_flags.csv").open())}
    SC = ["s55_project_ex_official", "cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider", "neo4jlabs", "pc_v1_1"]
    rows = []
    for stage in ("gate40", "ext260"):
        if not (work / ("replay_" + stage) / "scorer_verdicts_all.csv").exists():
            die("run the replay stage first (missing %s)" % (work / ("replay_" + stage)))
        V = {}
        for r in csv.DictReader((work / ("replay_" + stage) / "scorer_verdicts_all.csv").open()):
            V[(r["model"], r["question_id"], r["scorer"])] = (r["status"], r["verdict"])
        for t in jsonl(work / ("execution_" + stage) / "execution_traces.jsonl"):
            ref = t.get("reference") if isinstance(t.get("reference"), dict) else None
            e = t["errors"].get("prediction")
            err = (e.get("type") + ":" + e.get("message", "")[:60]) if isinstance(e, dict) else (e or "")
            row = {"stage": stage, "model": t["model"], "question_id": t["question_id"], "graph": t["graph"],
                   "near_overlap_flag": flags[t["question_id"]]["near_manual_train_jaccard_ge_0_8"], "near_cluster_id": flags[t["question_id"]]["internal_near_cluster_id"],
                   "baseline_status": t["status"], "candidate_error": err,
                   "reference_empty_or_all_null": "" if ref is None else str(int((not ref["rows"]) or all(c is None for r in ref["rows"] for c in r)))}
            for s in SC:
                st, v = V[(t["model"], t["question_id"], s)]
                row["status__" + s], row["verdict__" + s] = st, v
            rows.append(row)
    out = work / "case_study_units_reproduced.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    same = out.read_bytes() == (CS / "verdicts/case_study_units.csv").read_bytes()
    if not same:
        a_ = list(csv.DictReader(out.open())); b_ = list(csv.DictReader((CS / "verdicts/case_study_units.csv").open()))
        diff = [(x["stage"], x["model"], x["question_id"], k) for x, y in zip(a_, b_) for k in x if x[k] != y[k]]
        print(json.dumps({"stage": "table", "status": "DIFFERS", "n_cell_differences": len(diff), "first": diff[:10]}))
        sys.exit(1)
    rc = subprocess.run([sys.executable, "-B", str(CS / "code/recompute_case_study.py")]).returncode
    print(json.dumps({"stage": "table", "status": "PASS" if rc == 0 else "FAIL", "unit_table_byte_identical": True}))
    sys.exit(rc)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=("prepare", "execute", "replay", "table"))
    ap.add_argument("--work", default=str(ART / "work/model_output_case_study"))
    ap.add_argument("--mtq", default=str(ART / "external/mind_the_query"))
    ap.add_argument("--reuse-running", action="store_true", help="execute: reuse already provisioned s55j-gate260-* containers")
    ap.add_argument("--container-prefix", default="", help="execute: container name prefix instead of 's55j-gate260-' (e.g. 'repro-')")
    ap.add_argument("--port-base", type=int, default=0, help="execute: first loopback Bolt port instead of 17711")
    a = ap.parse_args()
    {"prepare": prepare, "execute": execute, "replay": replay, "table": table}[a.stage](a)


if __name__ == "__main__":
    main()
