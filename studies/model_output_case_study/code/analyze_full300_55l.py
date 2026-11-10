"""S55L full analysis: Gate40, ext260 and combined-300 under the frozen project metric and 9 replayed implementations.
Reads frozen traces and verdict CSVs only. Conventions marked POST-SCORING are not prospectively governed."""
import csv, itertools, json, math, random, re, sys
from collections import Counter, defaultdict
from pathlib import Path
T = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=False)
G = T / "gate40_scoring_runs"; J = lambda p: [json.loads(l) for l in Path(p).read_text().splitlines()]
STAGE = {"gate40": (G / "s55f_score_01/execution_traces.jsonl", G / "s55h_scorer_replay_01/scorer_verdicts_all.csv"),
         "ext260": (G / "s55l_score260_01/execution_traces.jsonl", G / "s55l_scorer_replay260_01/scorer_verdicts_all.csv")}
M = ("qwen", "mistral"); PROJ = "s55_project_ex_official"
CLASS = {PROJ: "project-authored (frozen metric)", "pc_v1_1": "project-authored comparator", "neo4jlabs": "third-party secondary",
         **{s: "third-party primary" for s in ("cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider")}}
SC = [PROJ, "cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider", "neo4jlabs", "pc_v1_1"]
flags = {r["question_id"]: (r["near_manual_train_jaccard_ge_0_8"] == "1", r["internal_near_cluster_id"]) for r in csv.DictReader((T / "data/near_overlap_flags.csv").open())}
U = {}   # (stage, model, qid) -> unit record
for st, (tp, vp) in STAGE.items():
    tr = {(t["model"], t["question_id"]): t for t in J(tp)}
    V = defaultdict(dict)
    for r in csv.DictReader(vp.open()): V[(r["model"], r["question_id"])][r["scorer"]] = (r["status"], r["verdict"])
    for (m, q), t in tr.items():
        ref = t.get("reference"); rr = ref["rows"] if isinstance(ref, dict) else None
        e = t["errors"].get("prediction"); etype = e.get("type") if isinstance(e, dict) else e
        emsg = e.get("message", "") if isinstance(e, dict) else ""
        code = re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`[^`]*`", " ", t.get("predicted_query") or "")
        semi_only = etype == "QueryRejected" and emsg == "disallowed construct" and set(h.upper() for h in re.findall(r"//|/\*|;|\b(?:CALL|CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD|FOREACH|USE|SHOW|APOC|DBMS)\b", code, re.I)) == {";"}
        sc = {}
        for s in SC:
            stt, v = V[(m, q)].get(s, (None, None))
            sc[s] = 1 if (stt == "supported_scored" and v == "1") else (0 if (stt in ("supported_scored", "execution_error", "extract_error") and v in ("0", "")) else None)
        # project: execution/extract error = 0; invalid_reference/unsupported = None (no score, frozen rule)
        U[(st, m, q)] = {"stage": st, "model": m, "qid": q, "graph": t["graph"], "status": t["status"], "sc": sc,
                         "weak_ref": (rr is not None and t["status"] in ("scored",) and ((not rr) or all(c is None for r in rr for c in r))),
                         "ref_valid": t["status"] not in ("invalid_reference",), "err_type": etype, "semicolon_only_rejection": semi_only,
                         "flagged": flags[q][0], "cluster": flags[q][1], "trace": t}
        # weak defined on the reference result whenever the reference executed (also for candidate errors)
        if t["status"] in ("execution_error", "unsupported", "extract_error") and isinstance(ref, dict):
            U[(st, m, q)]["weak_ref"] = (not rr) or all(c is None for r in rr for c in r)
qids = {st: sorted({q for (s, m, q) in U if s == st}) for st in STAGE}; qids["combined300"] = qids["gate40"] + qids["ext260"]
units = lambda st, m: [U[(s, m, q)] for s in (["gate40", "ext260"] if st == "combined300" else [st]) for q in qids[s]]
assert all(len(units(st, m)) == {"gate40": 40, "ext260": 260, "combined300": 300}[st] for st in qids for m in M)
res = {"stages": {}, "conventions": {
  "accepted": "verdict 1 under that column; execution/extract errors count as not accepted (frozen)",
  "no_score": "invalid_reference (gold failed/rejected/unsupported) and candidate-unsupported units carry no verdict (frozen rule); they are reported, never counted as model errors",
  "denominators_POST_SCORING": "N_total = all units; N_evaluable = units with a project-metric verdict; bounds [k/N_total, (k+u)/N_total], u = no-score units (by analogy to P5; not prospectively specified for invalid references)",
  "sensitivity_P2": "exclude units whose reference result is empty or all-NULL (reference executed); applied to all columns",
  "paired_set": "questions where BOTH models have a verdict under the column (invalid references are model-independent, so excluding them cannot favour either model)"}}
def acc_block(st, m, s, excl_weak=False):
    us = [u for u in units(st, m) if not (excl_weak and u["weak_ref"])]
    k = sum(u["sc"][s] == 1 for u in us); ev = [u for u in us if u["sc"][s] is not None]; nos = len(us) - len(ev)
    return {"k": k, "N_total": len(us), "N_evaluable": len(ev), "no_score": nos, "acc_evaluable": round(k / len(ev), 4) if ev else None,
            "bounds_total": [round(k / len(us), 4), round((k + nos) / len(us), 4)]}
for st in qids:
    S = res["stages"][st] = {"per_model": {}, "per_scorer": {}, "pairwise": {}, "ranking": {}, "overlap": {}, "graph": {}}
    for m in M:
        us = units(st, m)
        S["per_model"][m] = {"status_counts": dict(Counter(u["status"] for u in us)), "graph_counts": dict(Counter(u["graph"] for u in us)),
            "execution_error_types": dict(Counter(str(u["err_type"]) for u in us if u["status"] == "execution_error")),
            "semicolon_only_rejections": sum(u["semicolon_only_rejection"] for u in us), "weak_ref_units": sum(u["weak_ref"] for u in us),
            "primary": acc_block(st, m, PROJ), "sensitivity_excl_empty_allnull": acc_block(st, m, PROJ, True),
            "by_graph": {g: acc_block_g for g, acc_block_g in ((g, {"k": sum(u["sc"][PROJ] == 1 for u in us if u["graph"] == g), "N": sum(u["graph"] == g for u in us),
                          "evaluable": sum(u["sc"][PROJ] is not None for u in us if u["graph"] == g)}) for g in sorted({u["graph"] for u in us}))}}
    for s in SC:
        S["per_scorer"][s] = {"class": CLASS[s], **{m: {"primary": acc_block(st, m, s), "sensitivity": acc_block(st, m, s, True),
             "scorer_exceptions": sum(1 for u in units(st, m) if u["status"] == "scored" and u["sc"][s] is None)} for m in M}}
    comp = [u for m in M for u in units(st, m) if u["status"] == "scored"]
    for a, b in itertools.combinations(SC, 2):
        el = [u for u in comp if u["sc"][a] is not None and u["sc"][b] is not None]
        d = [u for u in el if u["sc"][a] != u["sc"][b]]
        S["pairwise"]["%s|%s" % (a, b)] = {"eligible": len(el), "disagree": len(d), "pct": round(100 * len(d) / len(el), 2) if el else None}
    # ranking statistics
    for s in SC:
        R = {}
        for view in ("primary", "sensitivity"):
            pairs = []
            for q in [q for sx in (["gate40", "ext260"] if st == "combined300" else [st]) for q in qids[sx]]:
                sx = "gate40" if q in set(qids["gate40"]) else "ext260"; a, b = U[(sx, "qwen", q)], U[(sx, "mistral", q)]
                if a["sc"][s] is None or b["sc"][s] is None: continue
                if view == "sensitivity" and (a["weak_ref"] or b["weak_ref"]): continue
                pairs.append((q, a["sc"][s] - b["sc"][s], a["graph"], a["cluster"]))
            n = len(pairs); diff = sum(p[1] for p in pairs)
            bq, cq = sum(p[1] == 1 for p in pairs), sum(p[1] == -1 for p in pairs)
            nd = bq + cq; pm = min(1.0, 2 * sum(math.comb(nd, i) for i in range(0, min(bq, cq) + 1)) / 2 ** nd) if nd else 1.0
            rng = random.Random(55); vals = [p[1] for p in pairs]
            qb = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(10000)) if n else []
            cl = defaultdict(list)
            for p in pairs: cl[p[3]].append(p[1])
            keys = sorted(cl); rng = random.Random(55); cb = []
            for _ in range(10000):
                pick = [keys[rng.randrange(len(keys))] for _ in keys]; tot = sum(sum(cl[k]) for k in pick); cnt = sum(len(cl[k]) for k in pick); cb.append(tot / cnt)
            cb.sort()
            side = lambda er: [p for p in pairs if (p[2] == "er") == er]
            R[view] = {"n_paired": n, "qwen_minus_mistral_count": diff, "mean_diff": round(diff / n, 4) if n else None,
                       "discordant_qwen_only": bq, "discordant_mistral_only": cq, "mcnemar_exact_p": round(pm, 6),
                       "question_bootstrap95": [round(qb[249], 4), round(qb[9749], 4)] if n else None, "cluster_bootstrap95": [round(cb[249], 4), round(cb[9749], 4)] if n else None,
                       "er": {"n": len(side(True)), "diff": sum(p[1] for p in side(True))}, "non_er": {"n": len(side(False)), "diff": sum(p[1] for p in side(False))}}
        S["ranking"][s] = R
    for m in M:
        us = units(st, m)
        S["overlap"][m] = {lab: {"N": len(g), "k": sum(u["sc"][PROJ] == 1 for u in g), "evaluable": sum(u["sc"][PROJ] is not None for u in g)}
                           for lab, g in (("flagged", [u for u in us if u["flagged"]]), ("unflagged", [u for u in us if not u["flagged"]]))}
# P3 decision on the pooled 300 (primary column = frozen project metric); assessability of (c) on paired COMPARABLE questions
def p3(s):
    R = res["stages"]["combined300"]["ranking"][s]; P, Sx = R["primary"], R["sensitivity"]
    sign = lambda x: (x > 0) - (x < 0)
    a = sign(P["qwen_minus_mistral_count"]) == sign(Sx["qwen_minus_mistral_count"]) != 0
    ex0 = lambda r: r["question_bootstrap95"][0] > 0 or r["question_bootstrap95"][1] < 0
    exc = lambda r: r["cluster_bootstrap95"][0] > 0 or r["cluster_bootstrap95"][1] < 0
    b = ex0(P) and exc(P) and ex0(Sx) and exc(Sx)
    comp_q = lambda er: sum(1 for st in ("gate40", "ext260") for q in qids[st] if (U[(st, "qwen", q)]["graph"] == "er") == er and U[(st, "qwen", q)]["status"] == "scored" and U[(st, "mistral", q)]["status"] == "scored")
    ne, nn = comp_q(True), comp_q(False)
    assess = ne >= 30 and nn >= 30
    c = (sign(P["er"]["diff"]) == sign(P["non_er"]["diff"]) == sign(P["qwen_minus_mistral_count"]) != 0) if assess else None
    strong = a and b and c is True
    return {"a_views_agree": a, "b_cis_exclude_0_both_views": b, "c_paired_comparable_er": ne, "c_paired_comparable_non_er": nn,
            "c_assessable": assess, "c_direction_consistent": c if assess else "not assessable", "strong_ranking_claim": strong,
            "label": "strong" if strong else ("tentative / er-dominated" if (a and b and not assess) else "no ranking established")}
res["P3_decision_combined300"] = {s: p3(s) for s in SC}
# disagreement casebook with mechanism features (ext260 + gate40)
def feats(t):
    r, p = t["reference"], t["prediction"]; rc, pc, rr, pr = r["columns"], p["columns"], r["rows"], p["rows"]
    key = lambda row: json.dumps(row, sort_keys=True); num = lambda row: json.dumps([float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else x for x in row], sort_keys=True)
    f = {"alias_differs": sorted(rc) != sorted(pc), "arity_equal": len(rc) == len(pc), "rows_ref": len(rr), "rows_pred": len(pr), "empty": not rr and not pr,
         "all_null": bool(rr) and all(c is None for row in rr for c in row), "same_rows_in_order": rr == pr,
         "same_multiset": Counter(map(key, rr)) == Counter(map(key, pr)), "same_set_not_multiset": set(map(key, rr)) == set(map(key, pr)) and Counter(map(key, rr)) != Counter(map(key, pr)),
         "equal_after_int_float": Counter(map(num, rr)) == Counter(map(num, pr)) and Counter(map(key, rr)) != Counter(map(key, pr)),
         "has_collections": any(isinstance(c, (list, dict)) for row in rr + pr for c in row)}
    import itertools as _it
    f["equal_after_column_permutation"] = (not f["same_multiset"]) and len(rc) == len(pc) and 1 < len(rc) <= 5 and any(
        Counter(map(key, rr)) == Counter(key([row[i] for i in perm]) for row in pr) for perm in _it.permutations(range(len(pc))))
    mech = []
    if f["empty"] and not f["arity_equal"]: mech.append("empty-result arity")
    elif f["same_multiset"] and f["alias_differs"]: mech.append("column alias")
    if f["same_multiset"] and not f["same_rows_in_order"]: mech.append("row order")
    if f["equal_after_column_permutation"]: mech.append("column order (positional comparison)")
    if f["same_set_not_multiset"]: mech.append("duplicates")
    if f["equal_after_int_float"]: mech.append("int/float type")
    if f["all_null"]: mech.append("all-NULL")
    if f["has_collections"]: mech.append("collections present")
    if not mech: mech.append("unclassified (no demonstrated mechanism)")
    return f, mech
book = []
for (st, m, q), u in sorted(U.items()):
    if u["status"] != "scored": continue
    vs = {s: u["sc"][s] for s in SC}
    if len({v for v in vs.values() if v is not None}) > 1 or any(v is None for v in vs.values()):
        f, mech = feats(u["trace"])
        book.append({"stage": st, "model": m, "question_id": q, "graph": u["graph"], "verdicts": vs, "features": f, "mechanisms": mech})
res["casebook_summary"] = {st: dict(Counter(mm for b in book if b["stage"] == st for mm in b["mechanisms"])) for st in STAGE}
res["casebook_units"] = {st: sum(b["stage"] == st for b in book) for st in STAGE}
(out / "full300_analysis.json").write_text(json.dumps(res, indent=1, default=str))
(out / "disagreement_casebook.json").write_text(json.dumps(book, indent=1, default=str))
for st in qids:
    for m in M:
        p = res["stages"][st]["per_model"][m]; print(st, m, "primary", {k: p["primary"][k] for k in ("k", "N_total", "N_evaluable", "acc_evaluable", "bounds_total")}, "| sens k", p["sensitivity_excl_empty_allnull"]["k"], "/", p["sensitivity_excl_empty_allnull"]["N_evaluable"], "| semicolon-only", p["semicolon_only_rejections"])
print("casebook", res["casebook_units"], res["casebook_summary"])
for s in SC:
    r = res["stages"]["combined300"]["ranking"][s]["primary"]; x = res["stages"]["combined300"]["ranking"][s]["sensitivity"]
    print(s.ljust(24), "n", r["n_paired"], "Q-M", r["qwen_minus_mistral_count"], "qCI", r["question_bootstrap95"], "cCI", r["cluster_bootstrap95"], "p", r["mcnemar_exact_p"], "| sens", x["qwen_minus_mistral_count"], x["question_bootstrap95"], x["cluster_bootstrap95"], "| P3:", res["P3_decision_combined300"][s]["label"])
print(json.dumps(res["P3_decision_combined300"][PROJ]))
