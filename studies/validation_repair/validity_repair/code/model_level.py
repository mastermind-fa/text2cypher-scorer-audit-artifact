#!/usr/bin/env python3
"""POST-HOC model-level sensitivity (the validation repair; plan frozen in model_level_sensitivity/PLAN.md before calculation).

  python3.12 studies/validation_repair/validity_repair/code/model_level.py
Population: 138 G0 held-out questions x 2 models (frozen S8C). Units without a Study-14 verdict are incorrect under
every scorer (standard EX). Writes model_level_sensitivity/{model_level_ex.csv, summary.json}."""
import csv, json, os
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
MAIN_AUDIT = os.path.join(ROOT, "studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final")
OUT = os.path.join(ROOT, "studies/validation_repair/validity_repair/model_level_sensitivity")
MODELS = ["qwen3-4b", "phi3.5-mini-instruct"]
P7 = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider"]
SEC = ["neo4jlabs", "pc_v1_1"]

g0 = {}
for m in MODELS:
    rs = [json.loads(l) for l in open(os.path.join(ROOT, f"withheld/pilot_predictions/predictions/extracted_{m}.jsonl"))]
    g0[m] = sorted({r["canonical_id"] for r in rs if r["graph_variant"] == "G0"})
assert g0[MODELS[0]] == g0[MODELS[1]] and len(g0[MODELS[0]]) == 138
Q = g0[MODELS[0]]
scored = {r["case_id"]: r for r in csv.DictReader(open(os.path.join(MAIN_AUDIT, "s2_results.csv")))}
not_scored = {u["unit_id"] for u in json.load(open(os.path.join(MAIN_AUDIT, "pairs/s2_not_scored_units.json")))}
for m in MODELS:  # coverage: every unit is either scored or not-scored, never both, never missing
    for q in Q:
        assert (f"S2-{m}|{q}" in scored) != (f"{m}|{q}" in not_scored), (m, q)

def verdict(m, q, s):
    r = scored.get(f"S2-{m}|{q}")
    return r[s] if r else "NOT_SCORED"

res = {"population": {"questions": len(Q), "units": 2 * len(Q),
                      "scored": {m: sum(f"S2-{m}|{q}" in scored for q in Q) for m in MODELS}}, "primary": {}, "s1_errors_excluded": {}}
table = []
for s in P7 + SEC:
    row = {"scorer": s}
    for m in MODELS:
        v = [verdict(m, q, s) for q in Q]
        k = sum(x == "1" for x in v); e = sum(x.startswith("ERROR") for x in v)
        row[f"{m}_correct"] = k; row[f"{m}_ex"] = round(k / len(Q), 4); row[f"{m}_errors"] = e
        res["s1_errors_excluded"].setdefault(s, {})[m] = round(k / (len(Q) - e), 4)
    gap = row[f"{MODELS[0]}_correct"] - row[f"{MODELS[1]}_correct"]
    row["gap_qwen_minus_phi_pp"] = round(100 * gap / len(Q), 2)
    row["higher"] = "qwen3-4b" if gap > 0 else ("phi3.5-mini-instruct" if gap < 0 else "tie")
    pairs = Counter((verdict(MODELS[0], q, s) == "1", verdict(MODELS[1], q, s) == "1") for q in Q)
    row.update({"both": pairs[(True, True)], "only_qwen": pairs[(True, False)], "only_phi": pairs[(False, True)], "neither": pairs[(False, False)]})
    table.append(row)
    res["primary"][s] = row
prim = [r for r in table if r["scorer"] in P7]
for m in MODELS:
    xs = [r[f"{m}_correct"] for r in prim]
    res.setdefault("range_across_primary", {})[m] = {"min": min(xs), "max": max(xs), "range_pp": round(100 * (max(xs) - min(xs)) / len(Q), 2),
        "min_scorer": [r["scorer"] for r in prim if r[f"{m}_correct"] == min(xs)], "max_scorer": [r["scorer"] for r in prim if r[f"{m}_correct"] == max(xs)]}
for lab, subset in (("all_primary", P7), ("without_cypherlens", [s for s in P7 if s != "cypherlens"])):
    order = {r["scorer"]: r["higher"] for r in table if r["scorer"] in subset}
    res.setdefault("ranking", {})[lab] = {"per_scorer": order, "ranking_changes": len(set(order.values())) > 1}
s1o = {s: ("qwen3-4b" if v[MODELS[0]] > v[MODELS[1]] else "phi3.5-mini-instruct" if v[MODELS[0]] < v[MODELS[1]] else "tie")
       for s, v in res["s1_errors_excluded"].items() if s in P7}
res["ranking"]["sensitivity_errors_excluded"] = {"per_scorer": s1o, "ranking_changes": len(set(s1o.values())) > 1}
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "model_level_ex.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(table[0])); w.writeheader(); w.writerows(table)
json.dump(res, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
for r in table: print(r)
print(json.dumps({k: res[k] for k in ("population", "range_across_primary", "ranking")}, indent=1))
