"""Frozen-protocol scorer-impact test: paired (alternative − project metric) accuracy per model, δ = 2 pp, question and
near-cluster bootstrap (10,000, seed 55), exact McNemar; primary (all evaluable) and Sensitivity A (unflagged near-overlap set).
Units: questions with a project-metric verdict and a verdict under the alternative (non-executing candidates = not accepted under both)."""
import csv, json, math, random, sys
from collections import defaultdict
from pathlib import Path
T = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=False)
G = T / "gate40_scoring_runs"; J = lambda p: [json.loads(l) for l in Path(p).read_text().splitlines()]
flags = {r["question_id"]: (r["near_manual_train_jaccard_ge_0_8"] == "1", r["internal_near_cluster_id"]) for r in csv.DictReader((T / "data/near_overlap_flags.csv").open())}
V = {}
for tp, vp, st in ((G / "s55f_score_01/execution_traces.jsonl", G / "s55h_scorer_replay_01/scorer_verdicts_all.csv", "gate40"),
                   (G / "s55l_score260_01/execution_traces.jsonl", G / "s55l_scorer_replay260_01/scorer_verdicts_all.csv", "ext260")):
    for r in csv.DictReader(vp.open()):
        v = 1 if (r["status"] == "supported_scored" and r["verdict"] == "1") else (0 if r["status"] in ("supported_scored", "execution_error", "extract_error") else None)
        V[(st, r["model"], r["question_id"], r["scorer"])] = v
PROJ = "s55_project_ex_official"; ALTS = sorted({k[3] for k in V} - {PROJ})
def stat(pairs):
    n = len(pairs); d = [a - p for _, a, p in pairs]; b = sum(x == 1 for x in d); c = sum(x == -1 for x in d)
    pm = min(1.0, 2 * sum(math.comb(b + c, i) for i in range(min(b, c) + 1)) / 2 ** (b + c)) if b + c else 1.0
    rng = random.Random(55); qb = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(10000))
    cl = defaultdict(list)
    for (q, a, p) in pairs: cl[flags[q][1]].append(a - p)
    ks = sorted(cl); rng = random.Random(55); cb = []
    for _ in range(10000):
        pick = [ks[rng.randrange(len(ks))] for _ in ks]; cb.append(sum(sum(cl[k]) for k in pick) / sum(len(cl[k]) for k in pick))
    cb.sort(); diff = sum(d) / n
    return {"n": n, "alt_minus_project_pp": round(100 * diff, 2), "alt_only": b, "project_only": c, "mcnemar_exact_p": round(pm, 6),
            "question_ci_pp": [round(100 * qb[249], 2), round(100 * qb[9749], 2)], "cluster_ci_pp": [round(100 * cb[249], 2), round(100 * cb[9749], 2)],
            "abs_point_ge_2pp": abs(diff) >= 0.02, "ci_excludes_0": (qb[249] > 0 or qb[9749] < 0) and (cb[249] > 0 or cb[9749] < 0)}
res = {}
for stage in ("gate40", "ext260", "combined300"):
    sts = ["gate40", "ext260"] if stage == "combined300" else [stage]
    for m in ("qwen", "mistral"):
        for alt in ALTS:
            for view in ("primary", "sensitivityA_unflagged"):
                pairs = [(q, V[(st, m, q, alt)], V[(st, m, q, PROJ)]) for (st, mm, q, s) in V if s == PROJ and mm == m and st in sts
                         and V[(st, m, q, PROJ)] is not None and V.get((st, m, q, alt)) is not None and (view == "primary" or not flags[q][0])]
                res["%s|%s|%s|%s" % (stage, m, alt, view)] = stat(sorted(pairs))
(out / "scorer_materiality.json").write_text(json.dumps(res, indent=1))
for k, v in res.items():
    if k.startswith("combined300"): print(k.ljust(52), v["n"], v["alt_minus_project_pp"], v["question_ci_pp"], v["cluster_ci_pp"], "p=%s" % v["mcnemar_exact_p"], "MATERIAL" if v["abs_point_ge_2pp"] and v["ci_excludes_0"] else "")
