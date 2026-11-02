#!/usr/bin/env python3
"""Compare the frozen original controlled suite with the query-consistent corrected suite (the validation repair; PLAN A3–A4).

  python3.12 studies/validation_repair/validity_repair/code/compare_s1.py
Writes s1_corrected/comparison.csv (one row per changed verdict), s1_corrected/s1_corrected_results.csv and summary.json."""
import csv, json, math, os
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
D = os.path.join(ROOT, "studies/validation_repair/validity_repair/s1_corrected")
FROZEN = os.path.join(ROOT, "studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final/s1_results.csv")
ERRATUM = os.path.join(ROOT, "artifact/staging/public/expected_outputs/s1_erratum.json")
SC = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider", "neo4jlabs", "pc_v1_1"]


def wilson(k, n, z=1.959964):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round((c - h) / d, 3), round((c + h) / d, 3)


cases = {json.loads(l)["case_id"]: json.loads(l) for l in open(os.path.join(D, "s1_corrected_cases.jsonl"))}
corrected = {k for k, c in cases.items() if "correction" in c}
frozen = {r["case_id"]: r for r in csv.DictReader(open(FROZEN))}
new = {s: {json.loads(l)["case_id"]: json.loads(l)["verdict"] for l in open(os.path.join(D, "results", f"{s}.jsonl"))} for s in SC}
v = lambda x: str(x)

with open(os.path.join(D, "s1_corrected_results.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["case_id", "dimension", "expected", "corrected_fixture"] + SC)
    for k in sorted(cases): w.writerow([k, cases[k]["dimension"], cases[k]["expected"], k in corrected] + [v(new[s][k]) for s in SC])

changes, control_diff = [], []
for s in SC:
    for k in cases:
        a, b = frozen[k][s], v(new[s][k])
        if a != b:
            (changes if k in corrected else control_diff).append({"scorer": s, "case_id": k, "dimension": cases[k]["dimension"],
                                                                  "expected": cases[k]["expected"], "original": a, "corrected": b})
with open(os.path.join(D, "comparison.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["scorer", "case_id", "dimension", "expected", "original", "corrected"]); w.writeheader(); w.writerows(changes + control_diff)

lab = [k for k in cases if cases[k]["expected"] in ("EQUIV", "NONEQUIV")]
ok = lambda verdict, exp: verdict == ("1" if exp == "EQUIV" else "0")
err9 = set(json.load(open(ERRATUM))["fixtures"])
agree = {}
for s in SC:
    ko = sum(ok(frozen[k][s], cases[k]["expected"]) for k in lab); kn = sum(ok(v(new[s][k]), cases[k]["expected"]) for k in lab)
    agree[s] = {"original": ko, "corrected": kn, "n": len(lab), "corrected_rate": round(kn / len(lab), 3),
                "corrected_wilson95": wilson(kn, len(lab)), "original_excl9_rate": round(sum(ok(frozen[k][s], cases[k]["expected"]) for k in lab if k not in err9) / len([k for k in lab if k not in err9]), 3)}
summary = {"fixtures": len(cases), "corrected_fixtures": len(corrected), "unaffected_control": len(cases) - len(corrected),
           "determinism_control_differences": len(control_diff),
           "verdict_changes_on_corrected_fixtures": dict(Counter(c["scorer"] for c in changes)),
           "verdict_changes_by_scorer_and_dimension": {s: dict(Counter(c["dimension"] for c in changes if c["scorer"] == s)) for s in SC},
           "oracle_agreement_106": agree,
           "errors_corrected_run": {s: sum(str(new[s][k]).startswith("ERROR") for k in cases) for s in SC}}
json.dump(summary, open(os.path.join(D, "summary.json"), "w"), indent=1)
print(json.dumps(summary, indent=1))
