"""S55D fail-closed Gate40 graph preflight and frozen-metric execution.

Offline verification is safe. --live-preflight and --score require distinct owner
authorization and a separately provisioned isolated Neo4j Enterprise instance.
This module does not start, restore, create, or delete databases.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import zipfile

from project_ex import VERSION, neo4j_executor
from score_predictions import (
    TRACK, RUNNER, sha, validate, reference_map, score_rows,
    analysis_rows, write_outputs,
)

ROOT = TRACK.parents[2]
PACKET = TRACK / "data/packet_mtq_gate40.jsonl"
RETURN = TRACK / "kaggle/gate40_returns/5rcjfasx"
ARCHIVE = ROOT / "s55_gate40_5rcjfasx_artifacts.zip"
ARCHIVE_SHA = "ae21250970efd73b1d0feaa74d119b986e576f7fe605baa6f1d8430cc51326e1"
METRIC_SHA = "58920a4194fdd65e13b667ba8be8ae6b015974214080b547180e154a4fccfb28"
ADAPTER_SHA = "38175e99f8d20cc7cddfa5f396969394ed56701c32d03211b7a84ede96099bb7"
GRAPH_MANIFEST = TRACK / "GATE40_THREE_GRAPH_MAPPING.json"
GRAPH_MANIFEST_SHA = "d69191236dd12f1e92a690296529bd64821871347203af761da0621826af6e5c"
GRAPH_IDS = frozenset(("er", "healthcare", "wwc"))
READ_TIMEOUT = 30.0


def frozen_inputs(mtq_source: Path, graph_manifest: Path = GRAPH_MANIFEST, dump_root: Path | None = None):
    """Validate all frozen bytes, original returned archive, IDs and graph route."""
    if sha(ARCHIVE) != ARCHIVE_SHA:
        raise ValueError("Gate40 archive hash drift")
    if sha(TRACK / "evaluation/project_ex.py") != METRIC_SHA:
        raise ValueError("frozen metric implementation drift")
    if sha(TRACK / "evaluation/score_predictions.py") != ADAPTER_SHA:
        raise ValueError("frozen adapter implementation drift")
    if sha(RUNNER) != "8dbdb19653c84246898572b3dc79f02b0a9c8a00967a466526a5be36cb781bbf":
        raise ValueError("frozen model runner drift")
    kaggle = TRACK / "kaggle"
    spec = importlib.util.spec_from_file_location("gate40_recovery", kaggle / "validate_gate40_recovery_55c.py")
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.path.insert(0, str(kaggle))
    try:
        spec.loader.exec_module(module)
        archive_audit = module.audit(ARCHIVE, RETURN, RETURN / "session55_gate40_pinned_runtime_fixed.ipynb")
    finally:
        sys.path.remove(str(kaggle))
    if archive_audit["status"] != "INTEGRITY_PASS_BOOTSTRAP_VARIANT":
        raise ValueError("returned archive not validated")
    packet, predictions = validate(PACKET, {
        "qwen": RETURN / "s55_qwen_mtq_gate40.jsonl",
        "mistral": RETURN / "s55_mistral_mtq_gate40.jsonl",
    })
    references = reference_map(mtq_source, packet)
    if sha(graph_manifest) != GRAPH_MANIFEST_SHA:
        raise ValueError("S55D graph manifest hash drift")
    manifest = json.loads(graph_manifest.read_text())
    if manifest.get("packet_sha256") != sha(PACKET) or set(manifest.get("graphs", {})) != GRAPH_IDS:
        raise ValueError("graph manifest or packet drift")
    ids = {g: [r["question_id"] for r in packet if r["graph"] == g] for g in GRAPH_IDS}
    for g in GRAPH_IDS:
        item = manifest["graphs"][g]
        if item["question_ids"] != ids[g] or item["question_count"] != len(ids[g]):
            raise ValueError("graph/question mapping drift")
        dump = (dump_root / item["dump_file"]) if dump_root else Path(item["observed_dump_path"])
        if sha(dump) != item["dump_sha256"]:
            raise ValueError("dump hash drift: " + g)
    if sum(map(len, ids.values())) != 40 or any(references[q][0] != g for g, questions in ids.items() for q in questions):
        raise ValueError("reference graph mismatch")
    return packet, predictions, references, manifest, archive_audit


def route_map(manifest, requested):
    """Require a one-to-one graph/database mapping; never fall back."""
    if set(requested) != GRAPH_IDS:
        raise ValueError("missing/unknown graph route")
    expected = {g: manifest["graphs"][g]["database"] for g in GRAPH_IDS}
    if requested != expected or len(set(requested.values())) != 3:
        raise ValueError("database route differs from frozen mapping or aliases two graphs")
    return requested


def fingerprint(driver, database):
    """Reproduce S23's graph fingerprint on one explicitly selected database."""
    def query(tx, cypher):
        return tx.run(cypher).data()
    with driver.session(database=database, default_access_mode="READ") as session:
        with session.begin_transaction(timeout=READ_TIMEOUT) as tx:
            nodes = query(tx, "MATCH (n) RETURN labels(n) AS l, properties(n) AS p")
            rels = query(tx, "MATCH (a)-[r]->(b) RETURN type(r) AS t, properties(r) AS p, elementId(a) AS a, elementId(b) AS b")
            labels = query(tx, "MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS c ORDER BY l")
            types = query(tx, "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY t")
            tx.rollback()
    blob = json.dumps(sorted(json.dumps(x, sort_keys=True, default=str) for x in nodes + rels))
    return {"nodes": len(nodes), "relationships": len(rels),
            "sha256": hashlib.sha256(blob.encode()).hexdigest(),
            "label_counts": {x["l"]: x["c"] for x in labels},
            "rel_type_counts": {x["t"]: x["c"] for x in types}}


def live_preflight(driver, manifest, routes, *, test_denial):
    """Only call after owner authorizes live read and rollback-only write test."""
    from neo4j.exceptions import Neo4jError
    with driver.session(database="system", default_access_mode="READ") as session:
        identity = session.run("SHOW CURRENT USER YIELD user, roles RETURN user, roles").single()
    if identity is None or set(identity["roles"] or []) != {"PUBLIC", "reader"}:
        raise ValueError("scoring credentials are not exclusively PUBLIC+reader")
    report = {}
    for graph in sorted(GRAPH_IDS):
        database = routes[graph]
        with driver.session(database=database, default_access_mode="READ") as session:
            with session.begin_transaction(timeout=READ_TIMEOUT) as tx:
                component = tx.run("CALL dbms.components() YIELD edition, versions RETURN edition, versions").single()
                tx.rollback()
        if component is None or str(component["edition"]).lower() != "enterprise" or "5.15.0" not in component["versions"]:
            raise ValueError("Neo4j version mismatch: " + graph)
        actual = fingerprint(driver, database)
        expected = manifest["graphs"][graph]["fingerprint"]
        if actual != expected:
            raise ValueError("live graph fingerprint mismatch: " + graph)
        report[graph] = {"database": database, "server_versions": component["versions"],
                         "edition": component["edition"], "reader_roles": sorted(identity["roles"]),
                         "fingerprint": actual}
        if test_denial:
            # The transaction is always rolled back. A successful CREATE still
            # means reader privileges failed and scoring must stop.
            denied = False
            # WRITE routing deliberately avoids a client-side READ-mode denial.
            # Only the server's Security.Forbidden code counts as evidence.
            with driver.session(database=database, default_access_mode="WRITE") as session:
                with session.begin_transaction(timeout=READ_TIMEOUT) as tx:
                    try:
                        tx.run("CREATE (:S55PermissionProbe)").consume()
                    except Neo4jError as exc:
                        denied = exc.code == "Neo.ClientError.Security.Forbidden"
                        if not denied:
                            raise
                    finally:
                        tx.rollback()
            if not denied:
                raise ValueError("database accepted write as scoring user: " + graph)
            report[graph]["write_denied"] = True
    return report


def summarize(traces):
    """Fixed 40-unit denominator per model, with invalid gates never scored."""
    by_model = {}
    for model in ("qwen", "mistral"):
        rows = [t for t in traces if t["model"] == model]
        if len(rows) != 40 or len({t["question_id"] for t in rows}) != 40:
            raise ValueError("incomplete or duplicate model verdicts")
        counts = Counter(t["status"] for t in rows)
        correct = sum(t["status"] == "scored" and t["verdict"] == 1 for t in rows)
        invalid = any(t["status"] in {"invalid_reference", "unsupported"} for t in rows)
        by_model[model] = {"correct": correct, "denominator": 40, "status_counts": dict(sorted(counts.items())),
                           "gate": "INVALID" if invalid else ("PASS" if correct >= 6 else "FAIL")}
    return by_model


def package_evidence(output_dir):
    """Package completed scoring files without changing or deleting them."""
    output_dir = Path(output_dir)
    names = ("execution_traces.jsonl", "scorer_verdicts.csv", "execution_manifest.json", "SHA256SUMS")
    if any(not (output_dir / name).is_file() for name in names):
        raise ValueError("scoring evidence incomplete")
    declared = {}
    for line in (output_dir / "SHA256SUMS").read_text().splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2 or parts[1] in declared:
            raise ValueError("invalid scoring checksum manifest")
        declared[parts[1]] = parts[0]
    if set(declared) != set(names) - {"SHA256SUMS"} or any(
        sha(output_dir / name) != digest for name, digest in declared.items()
    ):
        raise ValueError("scoring evidence hash mismatch")
    target = output_dir.with_suffix(".zip")
    if target.exists():
        raise ValueError("evidence ZIP exists; preserve prior evidence")
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.write(output_dir / name, arcname=name)
    with zipfile.ZipFile(target) as z:
        if set(z.namelist()) != set(names) or z.testzip() is not None:
            raise ValueError("evidence ZIP verification failed")
    return {"path": str(target), "sha256": sha(target), "bytes": target.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("offline-check", "live-preflight", "score"))
    parser.add_argument("--mtq-source", type=Path, required=True)
    parser.add_argument("--dump-root", type=Path, help="alternative directory of the same three hash-pinned dumps")
    parser.add_argument("--database-map", type=Path)
    parser.add_argument("--uri")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--owner-authorized-live", action="store_true")
    args = parser.parse_args()
    packet, predictions, references, manifest, archive_audit = frozen_inputs(args.mtq_source, dump_root=args.dump_root)
    if args.mode == "offline-check":
        print(json.dumps({"status": "OFFLINE_PASS", "scored": False,
                          "models": {k: len(v) for k, v in predictions.items()},
                          "graphs": {g: manifest["graphs"][g]["question_count"] for g in sorted(GRAPH_IDS)}}))
        return
    if not args.owner_authorized_live or not args.uri or not args.database_map or not args.output_dir:
        raise SystemExit("live mode requires separate owner authorization, URI, frozen database map and new output directory")
    if args.output_dir.exists():
        raise SystemExit("output directory exists; preserve prior evidence")
    if args.mode == "score" and args.output_dir.with_suffix(".zip").exists():
        raise SystemExit("evidence ZIP exists; preserve prior evidence")
    routes = route_map(manifest, json.loads(args.database_map.read_text()))
    user, password = os.environ.get("S55_NEO4J_READONLY_USER"), os.environ.get("S55_NEO4J_READONLY_PASSWORD")
    if not user or not password:
        raise SystemExit("reader credentials must be supplied outside repository")
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(args.uri, auth=(user, password))
    try:
        preflight = live_preflight(driver, manifest, routes, test_denial=True)
        if args.mode == "live-preflight":
            args.output_dir.mkdir(parents=True, exist_ok=False)
            (args.output_dir / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n")
            return
        traces, project_rows = score_rows(packet, predictions, references, neo4j_executor(driver, routes))
    finally:
        driver.close()
    if len(traces) != 80 or len(project_rows) != 80:
        raise ValueError("incomplete scoring trace")
    summary = summarize(traces)
    rows = analysis_rows(traces, project_rows, {})
    write_outputs(traces, rows, args.output_dir)
    execution_manifest = {"phase": "Gate40 native graph scoring", "metric": VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "archive_sha256": ARCHIVE_SHA, "packet_sha256": sha(PACKET),
        "qwen_prediction_sha256": sha(RETURN / "s55_qwen_mtq_gate40.jsonl"),
        "mistral_prediction_sha256": sha(RETURN / "s55_mistral_mtq_gate40.jsonl"),
        "evaluator_sha256": METRIC_SHA, "adapter_sha256": ADAPTER_SHA,
        "workflow_sha256": sha(Path(__file__)),
        "graph_manifest_sha256": sha(GRAPH_MANIFEST),
        "database_map_sha256": sha(args.database_map),
        "source_commit": "ec4054a1b7df7e6310efa95c56bb6e7cebc4d161",
        "graph_dump_sha256": {g: manifest["graphs"][g]["dump_sha256"] for g in sorted(GRAPH_IDS)},
        "preflight": preflight,
        "summary": summary, "trace_count": len(traces), "scored": True}
    (args.output_dir / "execution_manifest.json").write_text(json.dumps(execution_manifest, indent=2) + "\n")
    (args.output_dir / "SHA256SUMS").write_text("".join(
        f"{sha(args.output_dir / name)}  {name}\n" for name in
        ("execution_traces.jsonl", "scorer_verdicts.csv", "execution_manifest.json")))
    package = package_evidence(args.output_dir)
    print(json.dumps({"status": "SCORED", "summary": summary, "output": str(args.output_dir),
                      "evidence_zip": package}))


if __name__ == "__main__":
    main()
