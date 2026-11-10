"""S55M independent scientific audit. Fresh implementation from raw traces + raw native scorer outputs (not the 55L scripts or verdict CSVs).
No queries executed, no DB, no modification of any input."""
import csv, json, math, random, re, sys
from collections import Counter, defaultdict
from pathlib import Path
T = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=False)
G = T / "gate40_scoring_runs"; J = lambda p: [json.loads(l) for l in Path(p).read_text().splitlines()]
TR = {"gate40": J(G / "s55f_score_01/execution_traces.jsonl"), "ext260": J(G / "s55l_score260_01/execution_traces.jsonl")}
RAW = {"gate40": json.loads((G / "s55h_scorer_replay_01/raw_native_outputs.json").read_text()), "ext260": json.loads((G / "s55l_scorer_replay260_01/raw_native_outputs.json").read_text())}
FL = {r["question_id"]: (r["near_manual_train_jaccard_ge_0_8"] == "1", r["internal_near_cluster_id"]) for r in csv.DictReader((T / "data/near_overlap_flags.csv").open())}
SC = sorted(RAW["ext260"]); M = ("qwen", "mistral")
# ---------- unit table ----------
U = {}
for st, rows in TR.items():
    for t in rows:
        ref = t.get("reference") if isinstance(t.get("reference"), dict) else None
        e = t["errors"].get("prediction")
        U[(st, t["model"], t["question_id"])] = dict(st=st, m=t["model"], q=t["question_id"], g=t["graph"], status=t["status"], v=t["verdict"],
            ref_ok=t["status"] not in ("invalid_reference",) and (ref is not None or t["status"] == "extract_error"),
            cand_exec=t["status"] == "scored", pq=t.get("predicted_query"), rq=t["reference_query"],
            rej=(e.get("message") if isinstance(e, dict) and e.get("type") == "QueryRejected" else None),
            weak=ref is not None and ((not ref["rows"]) or all(c is None for r in ref["rows"] for c in r)))
def proj(u): return None if u["status"] in ("invalid_reference", "unsupported") else int(u["status"] == "scored" and u["v"] == 1)
def alt(u, s):
    if u["status"] in ("invalid_reference", "unsupported"): return None
    if not u["cand_exec"]: return 0                                     # non-executing candidate: not accepted under any scorer
    v = RAW[u["st"]][s]["%s|%s" % (u["m"], u["q"])]["verdict"]
    return v if v in (0, 1) else None                                    # exception -> no verdict (never a rejection)
stages = {"gate40": ["gate40"], "ext260": ["ext260"], "combined300": ["gate40", "ext260"]}
units = lambda stg, m: [u for (s, mm, q), u in U.items() if s in stages[stg] and mm == m]
res = {}
# ---------- 1. denominators ----------
D = {}
for stg in stages:
    for m in M:
        us = units(stg, m)
        D["%s|%s" % (stg, m)] = {"intended": len(us), "valid_reference": sum(u["status"] != "invalid_reference" for u in us),
            "valid_candidate_execution": sum(u["cand_exec"] for u in us), "candidate_extract_error": sum(u["status"] == "extract_error" for u in us),
            "candidate_execution_error": sum(u["status"] == "execution_error" for u in us), "candidate_unsupported": sum(u["status"] == "unsupported" for u in us),
            "invalid_reference": sum(u["status"] == "invalid_reference" for u in us), "project_evaluable": sum(proj(u) is not None for u in us),
            "project_accepted": sum(proj(u) == 1 for u in us),
            "scorer_eligible_pairs": {s: sum(1 for u in us if u["cand_exec"] and alt(u, s) is not None) for s in SC},
            "scorer_exceptions": {s: sum(1 for u in us if u["cand_exec"] and alt(u, s) is None) for s in SC}}
res["denominators"] = D
# ---------- 2. semicolon / filter audit ----------
def toks(q):
    code = re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`[^`]*`", " ", q or "")
    return sorted({h.upper() for h in re.findall(r"//|/\*|;|\b(?:CALL|CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD|FOREACH|USE|SHOW|APOC|DBMS)\b", code, re.I)}), code
F = {}
for stg in stages:
    for m in M:
        c = Counter(); trailing = 0; internal = 0
        for u in units(stg, m):
            if u["rej"]:
                tk, code = toks(u["pq"])
                if tk == [";"] and u["rej"] == "disallowed construct": lab = "semicolon_only"
                elif tk == [";"]: lab = "semicolon_present_but_rejected_as:" + u["rej"]
                elif u["rej"] == "missing RETURN": lab = "missing RETURN"
                elif "unterminated" in u["rej"]: lab = "unterminated literal"
                else: lab = "other:" + "+".join(tk)
                c[lab] += 1
                if tk == [";"] and u["rej"] == "disallowed construct":
                    if re.fullmatch(r"(?s).*[^;];\s*", code) and code.count(";") == 1: trailing += 1
                    else: internal += 1
        us = units(stg, m)
        F["%s|%s" % (stg, m)] = {"filter_rejections": sum(c.values()), "by_reason": dict(c), "semicolon_only_trailing_single": trailing, "semicolon_only_other_position_or_multiple": internal,
            "share_of_intended_units_semicolon_only": round(c["semicolon_only"] / len(us), 4), "reach_comparison_rate": round(sum(u["cand_exec"] for u in us) / len(us), 4)}
gold = Counter(); 
for u in units("combined300", "qwen"):
    if u["status"] == "invalid_reference":
        t = next(x for x in TR[u["st"]] if x["question_id"] == u["q"] and x["model"] == "qwen"); e = t["errors"]["reference"]
        gold[(e["type"], ("semicolon_only" if toks(u["rq"])[0] == [";"] else e["message"][:40]) if e["type"] == "QueryRejected" else e["type"])] += 1
F["gold_invalid_reference_reasons"] = {"%s|%s" % k: v for k, v in gold.items()}
res["filter_audit"] = F
# ---------- 3. materiality under three denominator conventions ----------
def mcnemar(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)
def boot_q(vals, seed=55, reps=10000):           # same scheme as the frozen spec (question-level, seed 55)
    rng = random.Random(seed); n = len(vals); d = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps)); return [d[249], d[9749]]
def boot_c(pairs, seed=55, reps=10000):          # near-cluster bootstrap
    cl = defaultdict(list)
    for q, x in pairs: cl[FL[q][1]].append(x)
    ks = sorted(cl); rng = random.Random(seed); d = []
    for _ in range(reps):
        pick = [ks[rng.randrange(len(ks))] for _ in ks]; d.append(sum(sum(cl[k]) for k in pick) / sum(len(cl[k]) for k in pick))
    d.sort(); return [d[249], d[9749]]
def boot_alt_seed(vals):                          # robustness: different seed, different resampler
    rng = random.Random(20261110); n = len(vals); d = sorted(sum(rng.choices(vals, k=n)) / n for _ in range(10000)); return [d[249], d[9749]]
MAT = {}
for stg in stages:
    for m in M:
        for s in SC:
            for view in ("all", "unflagged"):
                us = [u for u in units(stg, m) if view == "all" or not FL[u["q"]][0]]
                for conv in ("evaluable", "all_intended_zero_for_noscore", "both_executed_only"):
                    pr = []
                    for u in us:
                        p, a = proj(u), alt(u, s)
                        if conv == "evaluable":
                            if p is None or a is None: continue
                        elif conv == "all_intended_zero_for_noscore":
                            p = 0 if p is None else p; a = 0 if a is None else a
                        else:
                            if not u["cand_exec"] or p is None or a is None: continue
                        pr.append((u["q"], a - p))
                    vals = [x for _, x in pr]; n = len(vals); b = sum(x == 1 for x in vals); c = sum(x == -1 for x in vals)
                    qc = boot_q(vals) if n else [0, 0]; cc = boot_c(pr) if n else [0, 0]
                    MAT["%s|%s|%s|%s|%s" % (stg, m, s, view, conv)] = {"n": n, "pp": round(100 * sum(vals) / n, 2) if n else None, "alt_only": b, "proj_only": c,
                        "mcnemar_p": round(mcnemar(b, c), 6), "q_ci_pp": [round(100 * x, 2) for x in qc], "c_ci_pp": [round(100 * x, 2) for x in cc],
                        "material": bool(n) and abs(sum(vals) / n) >= 0.02 and (qc[0] > 0 or qc[1] < 0) and (cc[0] > 0 or cc[1] < 0)}
                    if conv == "evaluable" and n: MAT["%s|%s|%s|%s|%s" % (stg, m, s, view, conv)]["alt_seed_q_ci_pp"] = [round(100 * x, 2) for x in boot_alt_seed(vals)]
res["materiality"] = MAT
# ---------- 4. ranking + P3 ----------
RK = {}
for stg in stages:
    for view in ("primary", "sensitivity"):
        pr = []
        for q in sorted({u["q"] for u in units(stg, "qwen")}):
            st = "gate40" if ("gate40", "qwen", q) in U else "ext260"; a, b = U[(st, "qwen", q)], U[(st, "mistral", q)]
            if proj(a) is None or proj(b) is None: continue
            if view == "sensitivity" and (a["weak"] or b["weak"]): continue
            pr.append((q, proj(a) - proj(b), a["g"], a["cand_exec"] and b["cand_exec"]))
        vals = [x[1] for x in pr]; b_ = sum(x == 1 for x in vals); c_ = sum(x == -1 for x in vals)
        RK["%s|%s" % (stg, view)] = {"n": len(pr), "diff": sum(vals), "qwen_only": b_, "mistral_only": c_, "mcnemar_p": round(mcnemar(b_, c_), 6),
            "q_ci": [round(x, 4) for x in boot_q(vals)], "c_ci": [round(x, 4) for x in boot_c([(x[0], x[1]) for x in pr])],
            "er": {"n": sum(x[2] == "er" for x in pr), "diff": sum(x[1] for x in pr if x[2] == "er"), "paired_comparable": sum(x[2] == "er" and x[3] for x in pr)},
            "non_er": {"n": sum(x[2] != "er" for x in pr), "diff": sum(x[1] for x in pr if x[2] != "er"), "paired_comparable": sum(x[2] != "er" and x[3] for x in pr)}}
P, S = RK["combined300|primary"], RK["combined300|sensitivity"]
sg = lambda x: (x > 0) - (x < 0); ex = lambda r: (r["q_ci"][0] > 0 or r["q_ci"][1] < 0) and (r["c_ci"][0] > 0 or r["c_ci"][1] < 0)
assess = P["er"]["paired_comparable"] >= 30 and P["non_er"]["paired_comparable"] >= 30
res["P3"] = {"a": sg(P["diff"]) == sg(S["diff"]) != 0, "b": ex(P) and ex(S), "c_counts_paired_comparable": [P["er"]["paired_comparable"], P["non_er"]["paired_comparable"]],
             "c_assessable": assess, "decision": "strong" if (sg(P["diff"]) == sg(S["diff"]) != 0 and ex(P) and ex(S) and assess and sg(P["er"]["diff"]) == sg(P["non_er"]["diff"]) == sg(P["diff"])) else ("tentative / er-dominated" if not assess else "no ranking established")}
res["ranking"] = RK
(out / "audit_55m.json").write_text(json.dumps(res, indent=1, default=str))
# console summary
for k in ("combined300|qwen", "combined300|mistral", "ext260|qwen", "ext260|mistral"): print(k, {x: D[k][x] for x in ("intended", "valid_reference", "valid_candidate_execution", "project_evaluable", "project_accepted", "invalid_reference", "candidate_unsupported", "candidate_extract_error")})
for k in ("combined300|qwen", "combined300|mistral"): print(k, F[k])
print("gold", F["gold_invalid_reference_reasons"])
for k, v in MAT.items():
    if ("cypherturn" in k or "pipecypher" in k) and (k.startswith("combined300") or k.startswith("ext260")): print(k.ljust(64), v["n"], v["pp"], v["q_ci_pp"], v["c_ci_pp"], v.get("alt_seed_q_ci_pp", ""), "MATERIAL" if v["material"] else "-")
print("other scorers material anywhere (combined, any conv):", sorted({k.split("|")[2] for k, v in MAT.items() if v["material"] and k.startswith("combined300") and k.split("|")[2] not in ("cypherturn", "pipecypher")}))
for k, v in RK.items(): print(k, v)
print("P3", res["P3"])
