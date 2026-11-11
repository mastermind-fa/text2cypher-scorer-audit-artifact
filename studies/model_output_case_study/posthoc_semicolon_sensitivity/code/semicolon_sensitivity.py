#!/usr/bin/env python3
"""POST HOC sensitivity analysis of the model-output case study (paper Section VII, "Limits").

Question: how do the scorer shifts change if the project baseline's admission gate stops rejecting one trailing
semicolon? Neo4j 5.15.0 executes `RETURN 1 AS x;` (see studies/posthoc_minimal_cases/), so the frozen gate's `;` rule
removes queries that the engine would run.

What changes: ONLY the admission decision. One trailing `;` (plus whitespace) is stripped before the frozen
`read_only_query()` check; every other rule of the gate is unchanged, and the query sent to Neo4j is the original text.
Predictions, gold queries, graphs, comparators, adapters and the statistics code are those of the frozen study.

This analysis is NOT part of the frozen protocol. It was designed after the frozen results were known.

Stages (each refuses to overwrite its outputs):
  execute   run every gold and predicted query, read-only, on the four Neo4j 5.15.0 Community containers
            (same options as ../code/reproduce_case_study.py execute; run its `prepare` stage first)
  replay    re-run the nine pinned comparators on the new execution traces (released replay stage, unchanged)
  table     rebuild the per-unit table, compare it byte-for-byte with verdicts/case_study_units.csv, and recompute
            the statistics with the released recompute_case_study.py
usage: semicolon_sensitivity.py execute|replay|table [--work DIR] [--mtq DIR] [--reuse-running]
                                                     [--container-prefix P] [--port-base N]
"""
import argparse, csv, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]            # posthoc_semicolon_sensitivity/
CS = HERE.parent                                      # studies/model_output_case_study/
ART = CS.parents[1]
TRAILING = re.compile(r";\s*$")
SC = ["s55_project_ex_official", "cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens",
      "cyspider", "neo4jlabs", "pc_v1_1"]


def strip_trailing_semicolon(q):
    return TRAILING.sub("", q) if isinstance(q, str) else q


def load():
    sys.path.insert(0, str(CS / "code"))
    import project_ex, community_isolation_55j as iso, reproduce_case_study as rcs
    frozen = project_ex.read_only_query

    def gate(query):
        return frozen(strip_trailing_semicolon(query))
    project_ex.read_only_query = gate            # used by project_ex.evaluate()
    iso.read_only_query = gate                   # used by community_isolation_55j.admit()
    return rcs


def table(rcs, work):
    flags = {r["question_id"]: r for r in csv.DictReader((CS / "frozen/near_overlap_flags.csv").open())}
    rows = []
    for stage in ("gate40", "ext260"):
        V = {(r["model"], r["question_id"], r["scorer"]): (r["status"], r["verdict"])
             for r in csv.DictReader((work / ("replay_" + stage) / "scorer_verdicts_all.csv").open())}
        for t in rcs.jsonl(work / ("execution_" + stage) / "execution_traces.jsonl"):
            ref = t.get("reference") if isinstance(t.get("reference"), dict) else None
            e = t["errors"].get("prediction")
            err = (e.get("type") + ":" + e.get("message", "")[:60]) if isinstance(e, dict) else (e or "")
            row = {"stage": stage, "model": t["model"], "question_id": t["question_id"], "graph": t["graph"],
                   "near_overlap_flag": flags[t["question_id"]]["near_manual_train_jaccard_ge_0_8"],
                   "near_cluster_id": flags[t["question_id"]]["internal_near_cluster_id"],
                   "baseline_status": t["status"], "candidate_error": err,
                   "reference_empty_or_all_null": "" if ref is None else str(int((not ref["rows"]) or all(c is None for r in ref["rows"] for c in r)))}
            for s in SC:
                row["status__" + s], row["verdict__" + s] = V[(t["model"], t["question_id"], s)]
            rows.append(row)
    out = work / "case_study_units_posthoc_reproduced.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    same = out.read_bytes() == (HERE / "verdicts/case_study_units.csv").read_bytes()
    rc = subprocess.run([sys.executable, "-B", str(HERE / "code/recompute_case_study.py")]).returncode
    print(json.dumps({"stage": "table", "unit_table_byte_identical": same, "recompute": "PASS" if rc == 0 else "FAIL"}))
    sys.exit(0 if same and rc == 0 else 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=("execute", "replay", "table"))
    ap.add_argument("--work", default=str(ART / "work/model_output_case_study_posthoc_semicolon"))
    ap.add_argument("--mtq", default=str(ART / "external/mind_the_query"))
    ap.add_argument("--packets", default=str(ART / "work/model_output_case_study/packets"),
                    help="execute: packets directory written by `reproduce_case_study.py prepare`")
    ap.add_argument("--reuse-running", action="store_true")
    ap.add_argument("--container-prefix", default="")
    ap.add_argument("--port-base", type=int, default=0)
    a = ap.parse_args()
    rcs = load(); work = Path(a.work)
    if a.stage == "execute":
        if (work / "execute_manifest.json").exists():
            sys.exit("refusing: %s already executed" % work)
        work.mkdir(parents=True, exist_ok=True)
        if not (work / "packets").exists():
            import shutil; shutil.copytree(a.packets, work / "packets")
        rcs.execute(argparse.Namespace(work=str(work), mtq=a.mtq, reuse_running=a.reuse_running,
                                       container_prefix=a.container_prefix, port_base=a.port_base))
    elif a.stage == "replay":
        rcs.replay(argparse.Namespace(work=str(work)))
    else:
        table(rcs, work)


if __name__ == "__main__":
    main()
