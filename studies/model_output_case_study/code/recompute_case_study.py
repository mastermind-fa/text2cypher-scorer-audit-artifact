#!/usr/bin/env python3
"""Quick, network-free recomputation of the model-output case study (paper Section VII, Table IX) from
verdicts/case_study_units.csv. Reproduces per-scorer acceptances, paired accuracy shifts against the baseline with
question- and near-cluster bootstrap intervals (10,000 resamples, seed 55), exact McNemar and the ranking decision inputs,
and checks them against expected/expected_case_study.json.   usage: python3 code/recompute_case_study.py [--write-expected]"""
import csv, json, math, random, sys
from collections import defaultdict
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
U = list(csv.DictReader((HERE / "verdicts/case_study_units.csv").open()))
SC = ["s55_project_ex_official", "cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider", "neo4jlabs", "pc_v1_1"]
def v(u, s):   # 1 accepted, 0 not accepted (incl. non-executing candidate), None no verdict (invalid reference, unsupported, scorer exception)
    st, x = u["status__" + s], u["verdict__" + s]
    if st == "supported_scored": return int(x == "1")
    if st in ("execution_error", "extract_error"): return 0
    return None
def boot(pairs, cluster):
    vals = [d for _, d in pairs]; n = len(vals); rng = random.Random(55)
    qb = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(10000))
    cl = defaultdict(list)
    for q, d in pairs: cl[cluster[q]].append(d)
    ks = sorted(cl); rng = random.Random(55); cb = []
    for _ in range(10000):
        pick = [ks[rng.randrange(len(ks))] for _ in ks]; cb.append(sum(sum(cl[k]) for k in pick) / sum(len(cl[k]) for k in pick))
    cb.sort(); return [qb[249], qb[9749]], [cb[249], cb[9749]]
def mcnemar(b, c):
    n = b + c; return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)
cluster = {u["question_id"]: u["near_cluster_id"] for u in U}
res = {"acceptances": {}, "shifts": {}, "ranking": {}}
for stage in ("gate40", "ext260", "combined300"):
    us = [u for u in U if stage == "combined300" or u["stage"] == stage]
    for m in ("qwen", "mistral"):
        mu = [u for u in us if u["model"] == m]
        res["acceptances"]["%s|%s" % (stage, m)] = {s: sum(v(u, s) == 1 for u in mu) for s in SC}
        for s in SC[1:]:
            for view in ("all", "unflagged"):
                pairs = sorted((u["question_id"], v(u, s), v(u, SC[0])) for u in mu if v(u, SC[0]) is not None and v(u, s) is not None and (view == "all" or u["near_overlap_flag"] != "1"))
                pairs = [(q, a - p) for q, a, p in pairs]; qc, cc = boot(pairs, cluster)
                d = sum(x for _, x in pairs) / len(pairs)
                res["shifts"]["%s|%s|%s|%s" % (stage, m, s, view)] = {"n": len(pairs), "points": round(100 * d, 2), "q_ci": [round(100 * x, 2) for x in qc], "c_ci": [round(100 * x, 2) for x in cc],
                    "meets_2pt_with_cis_excluding_0": abs(d) >= 0.02 and (qc[0] > 0 or qc[1] < 0) and (cc[0] > 0 or cc[1] < 0)}
    by = {(u["model"], u["question_id"]): u for u in us}
    qs = [u["question_id"] for u in us if u["model"] == "qwen"]
    for view in ("primary", "excl_empty_all_null_reference"):
        pr = []
        for q in qs:
            a, b = by[("qwen", q)], by[("mistral", q)]
            if v(a, SC[0]) is None or v(b, SC[0]) is None: continue
            if view != "primary" and "1" in (a["reference_empty_or_all_null"], b["reference_empty_or_all_null"]): continue
            pr.append((q, v(a, SC[0]) - v(b, SC[0]), a["graph"], a["baseline_status"] == "scored" and b["baseline_status"] == "scored"))
        bq, cq = sum(x[1] == 1 for x in pr), sum(x[1] == -1 for x in pr)
        res["ranking"]["%s|%s" % (stage, view)] = {"n_paired": len(pr), "qwen_minus_mistral": bq - cq, "mcnemar_p": round(mcnemar(bq, cq), 6),
            "paired_comparable_er": sum(x[2] == "er" and x[3] for x in pr), "paired_comparable_non_er": sum(x[2] != "er" and x[3] for x in pr)}
exp = HERE / "expected/expected_case_study.json"
if "--write-expected" in sys.argv:
    exp.parent.mkdir(exist_ok=True); exp.write_text(json.dumps(res, indent=1, sort_keys=True)); print("expected written"); sys.exit(0)
ok = json.loads(exp.read_text()) == json.loads(json.dumps(res, sort_keys=True))
t = res["shifts"]; a = res["acceptances"]["combined300|qwen"], res["acceptances"]["combined300|mistral"]
print("Table IX check:", {s: (a[0][s], a[1][s]) for s in SC})
for k in ("combined300|qwen|cypherturn|all", "combined300|mistral|cypherturn|all", "combined300|qwen|pipecypher|all"): print(k, t[k])
print("RESULT:", "PASS (matches expected)" if ok else "FAIL (differs from expected)"); sys.exit(0 if ok else 1)
