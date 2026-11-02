#!/usr/bin/env python3
"""FULL / Level-1 re-scoring (artifact-full-rescore-v1): run every frozen scorer (via the frozen runner v1.1 + frozen
adapters) over a released pair file and compare each case's verdict with the frozen result CSV.
  python3 scripts/full_rescore.py s1            # synthetic suite (public)
  python3 scripts/full_rescore.py s3 <pairs>    # needs the CONDITIONAL corpus pairs (s3_pairs.jsonl)
  python3 scripts/full_rescore.py s2 <pairs>    # needs the CONDITIONAL S2 pairs (s2_pairs.jsonl)
Requires scorers fetched (third_party/fetch_scorers.sh). Writes to rebuild/<set>/ only; never touches frozen files."""
import csv, json, os, subprocess, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNNER = os.path.join(ROOT, "studies/corpus_audit/audit_analysis/code/run_experiment_v1_1.py")
MAIN_AUDIT = os.path.join(ROOT, "studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final")
SCORERS = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider", "neo4jlabs", "pc_v1_1"]
FROZEN = {"s1": "s1_results.csv", "s2": "s2_results.csv", "s3": "s3_results.csv"}


def main():
    st = sys.argv[1]
    inp = os.path.join(ROOT, "studies/controlled_suite/audit/s1/s1_cases.jsonl") if st == "s1" else sys.argv[2]
    out = os.path.join(ROOT, "rebuild", st); os.makedirs(out, exist_ok=True)
    frozen = {r["case_id"]: r for r in csv.DictReader(open(os.path.join(MAIN_AUDIT, FROZEN[st])))}
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="")
    bad = 0
    for s in SCORERS:
        rp = os.path.join(out, f"{s}.jsonl")
        subprocess.run([sys.executable, RUNNER, s, st, inp, rp], check=True, env=env)
        got = {json.loads(l)["case_id"]: str(json.loads(l)["verdict"]) for l in open(rp)}
        mism = [c for c, v in got.items() if frozen[c][s] != v]
        if len(got) != len(frozen): mism.append("CASE_COUNT")
        bad += len(mism)
        print(f"[{'OK' if not mism else 'FAIL'}] {st} {s}: {len(got)} cases, {len(mism)} mismatches {mism[:5]}")
    print(f"FULL {st}: {'PASS' if not bad else 'FAIL'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
