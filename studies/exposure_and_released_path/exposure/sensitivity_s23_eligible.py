#!/usr/bin/env python3
"""POST HOC sensitivity: exposure on the 1,086 Mind the Query sources eligible for the native suite
(native-suite rule: logical == "1" and result != "0" where present; distinct (graph, normalised query)). Uses the frozen
detector functions of exposure.py unchanged. The primary exposure population (all 1,829 test rows) is not replaced."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import exposure as E  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "../../.."))
P = E.load_parser(ROOT)
_, mq = E.load_mtq(ROOT, os.path.join(HERE, "mtq_results/mtq_gold_results.jsonl"))
lab = {}
import glob  # noqa: E402
for p in glob.glob(os.path.join(ROOT, "external/mind_the_query/Train_Test_Splits/Manual/*/test/*.json")):
    for r in json.load(open(p)):
        lab[r["unique_id"]] = (str(r.get("logical [0/1]")), str(r.get("result [0/1]", "1")))
seen, elig = set(), []
for it in mq:
    lg, rs = lab[it["item_id"]]
    q = it["query"].rstrip(";").rstrip()
    if lg != "1" or rs == "0" or (it["graph"], q) in seen:
        continue
    seen.add((it["graph"], q))
    elig.append(it)
rows, den = E.tally(elig, P, "Mind the Query: S23-eligible distinct sources (post hoc)")
out = {"note": "POST HOC sensitivity; primary population unchanged", "denominators": den, "counts": rows}
json.dump(out, open(os.path.join(HERE, "outputs_mtq_result_level/sensitivity_s23_eligible.json"), "w"), indent=1)
print(json.dumps(den))
for r in rows:
    print(r["level"], r["feature"], r["count"], r["denominator"], r["pct"])
