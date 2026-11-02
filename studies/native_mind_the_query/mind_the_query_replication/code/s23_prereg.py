#!/usr/bin/env python3
"""study S23 preregistration freeze (s23-prereg-v1). OFFLINE; no database, no scorer.

Freezes, BEFORE any Neo4j execution or scoring: the candidate file, the hashes of every S23 code file, the Mind the
Query source pin, the reference patterns (study S20 per class; S1 prior for new classes) computed from frozen CSVs,
the replication rubric text and the overlap report.
  python s23_prereg.py <candidates.jsonl> <mtq_dir> <overlap_report.json> <out_base_dir>
"""
import datetime, hashlib, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE)
import s23_replication as REP
from s23_rules import CLASSES, QUOTA, RESERVE, SEED, EPSILON_REL, GRAPHS

S20_VERDICTS = os.path.join(ROOT, "studies", "native_cypherturn_stress", "native_equivalence_stress", "frozen",
                            "20261030T143804Z_results", "s20_verdicts.csv")
S1_RESULTS = os.path.join(ROOT, "studies", "corpus_audit", "audit_final", "frozen", "20261029T190431Z_audit_final",
                          "s1_results.csv")
CODE = ["s23_parse.py", "s23_rules.py", "s23_oracle.py", "s23_replication.py", "s23_score.py", "s23_overlap.py"]


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    cand, mtq, overlap, out_base = sys.argv[1:5]
    commit = subprocess.run(["git", "-C", mtq, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    s20 = REP.patterns_from_csv(S20_VERDICTS, "class")
    import csv
    rows = {r["case_id"]: r for r in csv.DictReader(open(S1_RESULTS))}
    s1 = {cls: {s: REP.category([rows[i][s] for i in ids]) for s in REP.PRIMARY} for cls, ids in REP.NEW_CLASSES.items()}
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = os.path.join(out_base, f"{stamp}_preregistration"); os.makedirs(out)
    pre = {
        "session": "S23", "status": "FROZEN BEFORE ANY NEO4J EXECUTION OR SCORER RUN", "frozen_utc": stamp,
        "question": "Do the scorer-policy patterns observed on CypherTurn (study S20) recur on Mind the Query?",
        "source": {"benchmark": "Mind the Query (Chauhan et al., EMNLP 2025 Industry Track, pp. 1890-1905)",
                   "repository": "https://github.com/endeavorXx/Mind-the-Query", "commit": commit,
                   "licence_file": "LICENSE (Apache License 2.0) at the pinned commit; covers repository content. "
                                   "Underlying graph data come from neo4j-graph-examples repositories, which carry no "
                                   "licence file (GitHub API, 2026-10-31): dump licence UNVERIFIED.",
                   "split": "Train_Test_Splits/Manual/<graph>/test (sequential 70/30 split per split_statistics.txt)",
                   "eligibility": "logical [0/1] == '1' and result [0/1] != '0' where present",
                   "graphs_to_dumps": GRAPHS,
                   "dump_sha256": {g: sha(os.path.join(mtq, "Datasets", d)) for g, d in GRAPHS.items()},
                   "manual_test_files_sha256": {os.path.relpath(os.path.join(dp, f), mtq): sha(os.path.join(dp, f))
                                                for dp, _, fs in sorted(os.walk(os.path.join(mtq, "Train_Test_Splits", "Manual")))
                                                for f in sorted(fs) if f.endswith(".json") and os.sep + "test" + os.sep in os.path.join(dp, f)},
                   "db_schema_sha256": sha(os.path.join(mtq, "db_schema.jsonl")),
                   "license_sha256": sha(os.path.join(mtq, "LICENSE"))},
        "neo4j": {"image": "neo4j:5.15.0 (as study S18 and 20)", "load": "neo4j-admin database load (one graph at a "
                  "time into the throwaway container's 'neo4j' database)", "fallback": "none automatic; a load failure "
                  "stops the run and is reported to the owner"},
        "design": {"classes": CLASSES, "quota": QUOTA, "reserve": RESERVE, "seed": SEED, "epsilon_rel": EPSILON_REL,
                   "max_rows": 5000},
        "candidates_sha256": sha(cand),
        "code_sha256": {c: sha(os.path.join(HERE, c)) for c in CODE},
        "reference_patterns": {"s20_by_class": s20, "s1_prior_new_classes": s1,
                               "s20_source": os.path.relpath(S20_VERDICTS, ROOT), "s20_sha256": sha(S20_VERDICTS),
                               "s1_source": os.path.relpath(S1_RESULTS, ROOT), "s1_sha256": sha(S1_RESULTS)},
        "rubric": REP.__doc__,
        "class_mapping": {"shared_with_s20": REP.S20_MAP, "mechanism_level": REP.MECHANISM_CLASS,
                          "new_classes_s1_prior_case_ids": REP.NEW_CLASSES},
        "statistics": "descriptive only: exact counts, per scorer x class accept/reject with Wilson 95% CI, per-graph "
                      "counts; classes never pooled; no significance test; no population prevalence claim",
        "overlap_report_sha256": sha(overlap),
    }
    json.dump(pre, open(os.path.join(out, "preregistration.json"), "w"), indent=2)
    import shutil
    shutil.copy(overlap, os.path.join(out, "overlap_report.json"))
    shutil.copy(cand, os.path.join(out, "candidates.jsonl"))
    lines = [f"{sha(os.path.join(out, fn))}  {fn}" for fn in sorted(os.listdir(out))]
    open(os.path.join(out, "hashes.sha256"), "w").write("\n".join(lines) + "\n")
    print(json.dumps({"frozen": out, "hashes_sha256": sha(os.path.join(out, "hashes.sha256")),
                      "s20_patterns": s20, "s1_prior": s1}, indent=1))


if __name__ == "__main__":
    main()
