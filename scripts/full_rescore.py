#!/usr/bin/env python3
"""FULL / Level-1 re-scoring (artifact-full-rescore-v2): run every frozen scorer (via the frozen runner v1.1 + frozen
adapters) over a released pair file and compare each case's verdict with the frozen result CSV.
  python3 scripts/full_rescore.py s1_corrected  # query-consistent controlled suite (PAPER-FACING; public)
  python3 scripts/full_rescore.py s1            # original controlled suite (SUPERSEDED record; public)
  python3 scripts/full_rescore.py s3 <pairs>    # needs the dataset repository's corpus/s3_pairs.jsonl
  python3 scripts/full_rescore.py s2 <pairs>    # needs the dataset repository's model_outputs/s2_pairs.jsonl
Requires scorers fetched (third_party/fetch_scorers.sh). Writes to rebuild/<set>/ only; never touches frozen files.
For s1_corrected it also recomputes oracle agreement on the 106 labelled fixtures from the re-scored verdicts and fails
if the result equals the superseded original-suite values (regression guard: the paper reports the corrected suite)."""
import csv, json, os, subprocess, sys
ROOT = os.path.abspath(os.environ.get("ARTIFACT_ROOT") or os.path.join(os.path.dirname(__file__), ".."))
RUNNER = os.path.join(ROOT, "studies/corpus_audit/audit_analysis/code/run_experiment_v1_1.py")
MAIN_AUDIT = os.path.join(ROOT, "studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final")
S1C = os.path.join(ROOT, "studies/validation_repair/validity_repair/s1_corrected")
SCORERS = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider", "neo4jlabs", "pc_v1_1"]
# set -> (runner stage, input file or None = given on the command line, frozen verdict CSV)
SETS = {"s1": ("s1", os.path.join(ROOT, "studies/controlled_suite/audit/s1/s1_cases.jsonl"), os.path.join(MAIN_AUDIT, "s1_results.csv")),
        "s1_corrected": ("s1", os.path.join(S1C, "s1_corrected_cases.jsonl"), os.path.join(S1C, "s1_corrected_results.csv")),
        "s2": ("s2", None, os.path.join(MAIN_AUDIT, "s2_results.csv")),
        "s3": ("s3", None, os.path.join(MAIN_AUDIT, "s3_results.csv"))}


def agreement(verdicts, cases):
    lab = [k for k, c in cases.items() if c["expected"] in ("EQUIV", "NONEQUIV")]
    return {s: sum(verdicts[s][k] == ("1" if cases[k]["expected"] == "EQUIV" else "0") for k in lab) for s in verdicts}


def main():
    name = sys.argv[1]
    stage, inp, frozen_csv = SETS[name]
    inp = inp or sys.argv[2]
    out = os.path.join(ROOT, "rebuild", name); os.makedirs(out, exist_ok=True)
    frozen = {r["case_id"]: r for r in csv.DictReader(open(frozen_csv))}
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="")
    bad, verdicts = 0, {}
    for s in SCORERS:
        rp = os.path.join(out, f"{s}.jsonl")
        subprocess.run([sys.executable, RUNNER, s, stage, inp, rp], check=True, env=env)
        got = {json.loads(l)["case_id"]: str(json.loads(l)["verdict"]) for l in open(rp)}
        verdicts[s] = got
        mism = [c for c, v in got.items() if frozen[c][s] != v]
        if len(got) != len(frozen): mism.append("CASE_COUNT")
        bad += len(mism)
        print(f"[{'OK' if not mism else 'FAIL'}] {name} {s}: {len(got)} cases, {len(mism)} mismatches {mism[:5]}")
    if name == "s1_corrected":
        cases = {json.loads(l)["case_id"]: json.loads(l) for l in open(inp)}
        orig = {r["case_id"]: r for r in csv.DictReader(open(SETS["s1"][2]))}
        new = agreement(verdicts, cases)
        old = agreement({s: {k: orig[k][s] for k in cases} for s in SCORERS}, cases)
        exp = json.load(open(os.path.join(S1C, "summary.json")))["oracle_agreement_106"]
        ok_exp = all(new[s] == exp[s]["corrected"] for s in SCORERS)
        regress = new == old
        print(f"[{'OK' if ok_exp else 'FAIL'}] corrected-suite oracle agreement /106 from the re-scored verdicts: {new}")
        print(f"[{'OK' if not regress else 'FAIL'}] regression guard: differs from the superseded original suite {old}")
        bad += (not ok_exp) + regress
    print(f"FULL {name}: {'PASS' if not bad else 'FAIL'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
