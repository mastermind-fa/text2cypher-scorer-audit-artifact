#!/usr/bin/env python3
"""PAPER reproduction check (artifact-paper-v1): recompute every quantitative claim of the manuscript and supplement
from frozen verdict files and compare it with expected_outputs/paper_result_manifest.json. Exit 1 on any mismatch.

  python3 scripts/paper_check.py                       # layer A: inputs released in this repository
  python3 scripts/paper_check.py --dataset <DIR>       # + layer B: needs the released dataset repository
  python3 scripts/paper_check.py --dataset <DIR> --require-all   # fail if any claim could not be checked

Layers (each manifest entry names its layer):
  A   frozen verdicts released in this repository (no network, no Neo4j, no dataset repository)
  B   additionally needs ID-level files of the dataset repository (record provenance classes, unscored model units)
  R2  additionally needs native-Cypher inputs rebuilt by scripts/full_native.sh (CypherTurn / Mind the Query
      content is not redistributed); checked when rebuild/<stage>/ exists or the frozen input is present
A claim whose layer is unavailable is reported as BOUNDARY, never as PASS. The controlled-suite claims use the
query-consistent (corrected) suite; the original suite is checked only where the paper reports it as superseded, and a
regression check fails if the original values are reported as the current ones.
Read-only: writes nothing except rebuild/model_level/ (model-level table rebuilt from released unit IDs)."""
import argparse, csv, glob, hashlib, itertools, json, math, os, sys
from collections import Counter, defaultdict
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
P7 = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider"]
SIX = [s for s in P7 if s != "cypherlens"]
SEC = ["neo4jlabs", "pc_v1_1"]
Z = 2.8227  # pre-specified Bonferroni z (alpha = 0.05/21, one-sided); also read back from the frozen statistics

MAIN_AUDIT = "studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final"
S1O = "studies/controlled_suite/audit/s1/s1_cases.jsonl"
V = "studies/validation_repair/validity_repair"
S18R = "studies/native_cypherturn_validation/native_cypher/frozen/20261030T083338Z_native_cypher_results"
S20R = "studies/native_cypherturn_stress/native_equivalence_stress/frozen/20261030T143804Z_results"
S2S = "studies/native_cypherturn_stress/native_equivalence_stress/frozen/20261030T143405Z_s2_sensitivity"
S23 = "studies/native_mind_the_query/mind_the_query_replication"
S23R = S23 + "/frozen/20261031T181038Z_results"
S23I = S23 + "/frozen/20261031T180759Z_input"
S23P = S23 + "/frozen/20261031T175346Z_preregistration"


class Ctx:
    def __init__(self, root, dataset):
        self.root, self.dataset = root, dataset

    def p(self, rel): return os.path.join(self.root, rel)
    def csv(self, rel): return list(csv.DictReader(open(self.p(rel), encoding="utf-8")))
    def jl(self, rel): return [json.loads(l) for l in open(self.p(rel), encoding="utf-8")]
    def js(self, rel): return json.load(open(self.p(rel), encoding="utf-8"))

    def d(self, rel):
        if not self.dataset: raise Boundary("needs the dataset repository (--dataset DIR)")
        f = os.path.join(self.dataset, rel)
        if not os.path.exists(f): raise Boundary(f"dataset file missing: {rel}")
        return f


class Boundary(Exception):
    pass


def wilson(k, n, z):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def r3(x): return f"{x:.3f}"


def oracle_agreement(rows, scorers):
    lab = [r for r in rows if r["expected"] in ("EQUIV", "NONEQUIV")]
    return {s: sum(r[s] == ("1" if r["expected"] == "EQUIV" else "0") for r in lab) for s in scorers}


# ------------------------------------------------------------------------------------------------ controlled suite
def s1_claims(c):
    orig_cases = {x["case_id"]: x for x in c.jl(S1O)}
    corr_cases = {x["case_id"]: x for x in c.jl(V + "/s1_corrected/s1_corrected_cases.jsonl")}
    corr = {r["case_id"]: r for r in c.csv(V + "/s1_corrected/s1_corrected_results.csv")}
    orig = {r["case_id"]: r for r in c.csv(MAIN_AUDIT + "/s1_results.csv")}
    # the per-scorer raw result files must agree with the corrected results table
    raw_ok = all({json.loads(l)["case_id"]: str(json.loads(l)["verdict"])
                  for l in open(c.p(f"{V}/s1_corrected/results/{s}.jsonl"))} == {k: r[s] for k, r in corr.items()}
                 for s in P7 + SEC)
    man = c.csv(V + "/s1_corrected/correction_manifest.csv")
    head = lambda q: q.split("RETURN")[0]
    renamed = [m for m in man if head(m["original_pred_query"]) != head(m["corrected_pred_query"])
               or head(m["original_ref_query"]) != head(m["corrected_ref_query"])]
    corrected_ids = {m["case_id"] for m in man}
    identical = sorted(k for k, x in orig_cases.items() if x["ref_query"] == x["pred_query"])
    control = [k for k in corr if k not in corrected_ids]
    control_diffs = sum(corr[k][s] != orig[k][s] for k in control for s in P7 + SEC)
    changes = [(s, k) for k in corrected_ids for s in P7 + SEC if corr[k][s] != orig[k][s]]
    other = Counter(s for s, k in changes if s != "cypherlens")
    e = Counter(x["expected"] for x in corr_cases.values())
    ag_c, ag_o = oracle_agreement(corr.values(), P7 + SEC), oracle_agreement(orig.values(), P7 + SEC)

    def split(rows, s):
        lab = lambda exp: [r for r in rows if r["expected"] == exp]
        return [sum(r[s] == "1" for r in lab("EQUIV")), sum(r[s] == "0" for r in lab("NONEQUIV")),
                sum(r[s].startswith("ERROR") for r in rows)]
    vec = lambda k: "".join(corr[k][s] for s in P7)
    cl = lambda pre: [corr[k]["cypherlens"] for k in sorted(corr) if corr[k]["dimension"].startswith(pre)]
    return {
        "s1.suite": {"fixtures": len(corr_cases), "equiv": e["EQUIV"], "nonequiv": e["NONEQUIV"], "intent_dependent": e["INTENT_DEPENDENT"],
                     "dimension_groups": len({x["dimension"].split("_")[0] for x in corr_cases.values()}),
                     "sub_dimensions": len({x["dimension"] for x in corr_cases.values()}),
                     "same_case_ids_as_original": sorted(corr_cases) == sorted(orig_cases)},
        "s1c.correction": {"corrected": len(man), "alias_inconsistent": sum("aliases" in m["problem"] for m in man),
                           "identical_text": sum("identical" in m["problem"] for m in man),
                           "identical_text_fixtures": identical, "renamed_bound_variable": len(renamed),
                           "results_or_labels_changed": sum(m["result_values_changed"] != "NO" or m["oracle_changed"] != "NO" for m in man),
                           "unaffected_control": len(control), "control_verdict_differences": control_diffs,
                           "raw_result_files_match_table": raw_ok},
        "s1c.verdict_changes": {"cypherlens": sum(s == "cypherlens" for s, _ in changes), "other_scorers_changed": len(other),
                                "other_changes_only_on_identical_text": all(k in identical for s, k in changes if s != "cypherlens")},
        "s1c.oracle_agreement_106": ag_c,
        "s1o.oracle_agreement_106_superseded": ag_o,
        "s1c.regression_corrected_is_not_original": {s: ag_c[s] != ag_o[s] for s in ["cypherturn", "cypherbench", "gqlbench", "tugraph", "cypherlens", "cyspider"]},
        "s1c.supplement_SB": {s: {"corrected": split(corr.values(), s), "original": split(orig.values(), s)[:2]} for s in P7 + SEC},
        "s1c.table1_rows": {k: vec(k) for k in ["S1-007", "S1-019", "S1-057", "S1-061", "S1-040"]},
        "s1c.cypherlens_policy": {"alias_and_unaliased_key_accepted": cl("D02") + cl("D03") == ["1"] * 12,
                                  "order_required_accepted": cl("D06") == ["1"] * 4, "int_float_rejected": cl("D12") == ["0"] * 4},
    }


# ------------------------------------------------------------------------------------------------ corpus (S3)
def pair_stats(rows, a, b, z):
    k = sum(r[a] != r[b] for r in rows); n = len(rows)
    lo1, _ = wilson(k, n, z); lo, hi = wilson(k, n, 1.959964)
    return k, lo1, (lo, hi)


def mech(r):
    rej = tuple(s for s in SIX if r[s] == "0"); f = set(r["features"].split(";"))
    if "float_only_tiny_difference" in f and rej == tuple(s for s in SIX if s != "tugraph"): return "float_tiny_tg_only"
    if "key_name_difference" in f and rej == ("cypherturn",): return "naming_ct_only"
    if "key_name_difference" in f and rej == ("cypherturn", "pipecypher"): return "naming_with_order_triggers"
    if "null_present" in f and rej == ("gqlbench",): return "numeric_null_gq_only"
    if "int_float_type_difference" in f: return "int_float"
    if "row_order_difference" in f and rej == ("cypherbench", "gqlbench", "tugraph"): return "tie_order_with_triggers"
    if "row_order_difference" in f and rej == ("cypherbench", "gqlbench"): return "reference_order_cb_gq_only"
    if rej == ("tugraph",) and "order_by_in_prediction" in f: return "tg_prediction_trigger_only"
    return "UNCLASSIFIED"


def s3_claims(c):
    rows = c.csv(MAIN_AUDIT + "/s3_results.csv")
    st = c.js(MAIN_AUDIT + "/audit_statistics.json")["s3"]
    z = st["h1"]["z"]
    n = len(rows)
    passes = {s: sum(r[s] == "1" for r in rows) for s in P7}
    un = [r for r in rows if len({r[s] for s in P7}) == 1]
    pairs = {}
    for a, b in itertools.combinations(P7, 2):
        k, lb, ci = pair_stats(rows, a, b, z)
        pairs[f"{a}|{b}"] = {"k": k, "rate": r3(k / n), "lb": r3(lb), "ci95": [r3(ci[0]), r3(ci[1])], "meets": lb >= 0.02}
    cl_pairs = [v for p, v in pairs.items() if "cypherlens" in p]; ncl = [v for p, v in pairs.items() if "cypherlens" not in p]
    non6 = [r for r in rows if len({r[s] for s in SIX}) > 1]
    k_ct_tg, lb_ct_tg, _ = pair_stats(rows, "cypherturn", "tugraph", z)
    fro = {(r["scorer_a"], r["scorer_b"]): r for r in c.csv(MAIN_AUDIT + "/s3_pairwise_disagreement.csv")}
    frozen_ok = all(int((fro.get((a, b)) or fro.get((b, a)))["disagreements"]) == pairs[f"{a}|{b}"]["k"] for a, b in itertools.combinations(P7, 2))
    return {
        "s3.n": n,
        "s3.pass_counts": passes,
        "s3.unanimous": {"all": len(un), "pass": sum(r["cypherturn"] == "1" for r in un), "fail": sum(r["cypherturn"] == "0" for r in un)},
        "s3.criterion": {"z": z, "threshold": 0.02, "pairs_meeting": sum(v["meets"] for v in pairs.values()), "pairs_total": len(pairs),
                         "meeting_with_cypherlens": sum(v["meets"] for v in cl_pairs), "meeting_without_cypherlens": sum(v["meets"] for v in ncl),
                         "frozen_pairwise_table_matches": frozen_ok},
        "s3.pairwise_table_SA": pairs,
        "s3.rate_ranges": {"with_cypherlens": [min(v["rate"] for v in cl_pairs), max(v["rate"] for v in cl_pairs)],
                           "without_cypherlens": [min(v["rate"] for v in ncl), max(v["rate"] for v in ncl)],
                           "all": [min(v["rate"] for v in pairs.values()), max(v["rate"] for v in pairs.values())],
                           "max_in_domain_pct": f"{100 * max(v['k'] for v in ncl) / n:.1f}",
                           "cypherlens_pct": [f"{100 * min(v['k'] for v in cl_pairs) / n:.0f}", f"{100 * max(v['k'] for v in cl_pairs) / n:.0f}"]},
        "s3.six_scorer_nonunanimous": {"k": len(non6), "pct": f"{100 * len(non6) / n:.1f}"},
        "s3.ct_vs_tg": {"k": k_ct_tg, "pct": f"{100 * k_ct_tg / n:.2f}", "lb_pct": f"{100 * lb_ct_tg:.2f}"},
        "s3.cypherlens_only_failures": sum(r["cypherlens"] == "0" and all(r[s] == "1" for s in SIX) for r in rows),
        "s3.score_level_pct": {s: f"{100 * passes[s] / n:.1f}" for s in P7} | {"six_scorer_spread_pp": f"{100 * (max(passes[s] for s in SIX) - min(passes[s] for s in SIX)) / n:.1f}"},
        "s3.mechanisms_41": dict(sorted(Counter(mech(r) for r in non6).items())),
        "s3.empty_side_pairs": sum("empty_side" in r["features"] for r in rows),
    }


# ------------------------------------------------------------------------------------------------ Text2GQL evaluators
def t2g_claims(c):
    ea = c.csv(V + "/text2gql/ea_cypher_verdicts.csv")
    by = defaultdict(list)
    for r in ea: by[r["set"]].append(r)
    dis = lambda st: sum(r["agree"] == "False" for r in by[st])
    cls = lambda st: {k: v for k, v in sorted(Counter(r["class"] for r in by[st] if r["agree"] == "False").items())}
    # the driver column of the second-evaluator file must equal the frozen driver verdicts it was compared with
    frozen_tg = {}
    for st, f in [("s1_corrected", V + "/s1_corrected/s1_corrected_results.csv"), ("s3", MAIN_AUDIT + "/s3_results.csv"), ("s2", MAIN_AUDIT + "/s2_results.csv"),
                  ("s20", S20R + "/s20_verdicts.csv"), ("s23", S23R + "/s23_verdicts.csv"), ("s18", S18R + "/s18_verdicts.csv"),
                  ("s1_original", MAIN_AUDIT + "/s1_results.csv")]:
        fz = {r["case_id"]: r["tugraph"] for r in c.csv(f)}
        frozen_tg[st] = all(fz[r["case_id"]] == r["metrics_py_verdict"] for r in by[st]) and len(fz) == len(by[st])
    s3 = {r["case_id"]: r for r in c.csv(MAIN_AUDIT + "/s3_results.csv")}
    for r in by["s3"]: s3[r["case_id"]]["tg_ref"] = r["ea_cypher_verdict"]
    rows = list(s3.values()); z = c.js(MAIN_AUDIT + "/audit_statistics.json")["s3"]["h1"]["z"]
    sub = ["cypherturn", "cypherbench", "gqlbench", "tg_ref", "pipecypher", "cyspider"]
    meet = {(a, b) for a, b in itertools.combinations(sub, 2) if pair_stats(rows, a, b, z)[1] >= .02}
    meet0 = {(a, b) for a, b in itertools.combinations(SIX, 2) if pair_stats(rows, a, b, z)[1] >= .02}
    d3 = [r for r in by["s3"] if r["agree"] == "False"]
    return {
        "t2g.corpus": {"driver_accept": sum(r["metrics_py_verdict"] == "1" for r in by["s3"]),
                       "reference_accept": sum(r["ea_cypher_verdict"] == "1" for r in by["s3"]), "differ": len(d3),
                       "all_differences_reference_accepts_driver_rejects": all(r["ea_cypher_verdict"] == "1" and r["metrics_py_verdict"] == "0" for r in d3),
                       "driver_pct": f"{100 * sum(r['metrics_py_verdict'] == '1' for r in by['s3']) / 563:.1f}",
                       "reference_pct": f"{100 * sum(r['ea_cypher_verdict'] == '1' for r in by['s3']) / 563:.1f}"},
        "t2g.disagreements": {st: [dis(st), len(by[st])] for st in ["s1_corrected", "s18", "s20", "s23", "s2", "s3"]},
        "t2g.disagreement_classes": {st: cls(st) for st in ["s1_corrected", "s20", "s23"]},
        "t2g.driver_column_equals_frozen_driver": frozen_tg,
        "t2g.substitution": {"pairs_meeting": len(meet), "different_set": meet != meet0,
                             "nonunanimous": sum(len({r[s] for s in sub}) > 1 for r in rows)},
        "t2g.summary_matches_verdicts": all(v["disagreements"] == dis(k) and v["n"] == len(by[k])
                                            for k, v in c.js(V + "/text2gql/ea_cypher_summary.json")["sets"].items()),
    }


# ------------------------------------------------------------------------------------------------ model outputs (S2)
def s2_claims(c):
    rows = c.csv(MAIN_AUDIT + "/s2_results.csv")
    res = c.js(S2S + "/s2_sensitivity_results.json")
    ids = set(res["informative_case_ids"])
    inf = [r for r in rows if r["case_id"] in ids]
    complete = [r for r in rows if all(r[s] in ("0", "1") for s in P7)]
    nonu = [r for r in inf if len({r[s] for s in P7}) > 1]
    acc = {s: sum(r[s] == "1" for r in inf) for s in P7}
    lo, hi = wilson(len(nonu), len(inf), 1.959964)
    return {
        "s2.counts": {"predictions": len(rows), "empty": sum(r["empty_prediction"] == "True" for r in rows), "complete": len(complete),
                      "cyspider_errors": sum(r["cyspider"].startswith("ERROR") for r in rows)},
        "s2.informative": {"N": len(inf), "qwen3-4b": sum(r["model"] == "qwen3-4b" for r in inf),
                           "phi3.5-mini-instruct": sum(r["model"] == "phi3.5-mini-instruct" for r in inf),
                           "distinct_questions": len({r["case_id"].split("|")[1] for r in inf}),
                           "unanimous": len(inf) - len(nonu), "non_unanimous": len(nonu), "fraction": r3(len(nonu) / len(inf)),
                           "wilson95": [r3(lo), r3(hi)], "subset_definition_matches": res["primary_informative_subset"]["N"] == len(inf)},
        "s2.breakdown": {"cypherlens_only_accept": sum(r["cypherlens"] == "1" and all(r[s] == "0" for s in SIX) for r in nonu),
                         "cypherturn_rejects_others_accept": sum(r["cypherturn"] == "0" and all(r[s] == "1" for s in SIX if s != "cypherturn") for r in nonu),
                         "of_which_cypherlens_also_rejects": sum(r["cypherturn"] == "0" and r["cypherlens"] == "0" and all(r[s] == "1" for s in SIX if s != "cypherturn") for r in nonu),
                         "non_unanimous_without_cypherlens": sum(len({r[s] for s in SIX}) > 1 for r in inf)},
        "s2.complete_nonunanimous": {"all": sum(len({r[s] for s in P7}) > 1 for r in complete),
                                     "without_cypherlens": sum(len({r[s] for s in SIX}) > 1 for r in complete)},
        "s2.acceptances": acc,
        "s2.acceptance_gap": {"all": r3((max(acc.values()) - min(acc.values())) / len(inf)),
                              "without_cypherlens": r3((max(acc[s] for s in SIX) - min(acc[s] for s in SIX)) / len(inf))},
    }


def model_level_claims(c, write_dir):
    """Rebuild the model-level table from released unit IDs (scored S2 case IDs + unscored unit IDs), applying the frozen
    model_level.py logic unchanged except for where the 138 question IDs come from (see model_level_from_ids)."""
    sys.path.insert(0, HERE)
    from model_level_from_ids import rebuild
    out = rebuild(c.root, c.d("model_outputs/s2_not_scored_units.json"), write_dir)
    s2 = c.csv(MAIN_AUDIT + "/s2_results.csv")
    q = [x for x in s2 if x["model"] == "qwen3-4b" and x["cypherlens"] == "1"]
    only = [x for x in q if all(x[s] != "1" for s in SIX)]
    t = out["table"]
    return {
        "ml.population": out["summary"]["population"],
        "ml.credits": {s: [int(t[s]["qwen3-4b_correct"]), int(t[s]["phi3.5-mini-instruct_correct"])] for s in P7},
        "ml.cypherlens_qwen": {"credits": len(q), "accepted_by_no_other_primary": len(only),
                               "of_which_empty_prediction": sum(x["empty_prediction"] == "True" for x in only)},
        "ml.rebuilt_equals_frozen": out["byte_identical"],
    }


# ------------------------------------------------------------------------------------------------ provenance (S3 x records)
def provenance_claims(c):
    sp = list(csv.DictReader(open(c.d("splits/record_splits.csv"), encoding="utf-8")))
    cls = {r["record_id"]: r["provenance_class"] for r in sp}
    rows = c.csv(MAIN_AUDIT + "/s3_results.csv")
    rid = lambda r: "WC-" + r["case_id"].split("-")[1]
    grp = lambda r: "project" if cls[rid(r)].startswith("R-C") or "project" in cls[rid(r)] else "bird"
    by = defaultdict(list)
    for r in rows: by[grp(r)].append(r)
    non = lambda rs: sum(len({r[s] for s in SIX}) > 1 for r in rs)
    z = c.js(MAIN_AUDIT + "/audit_statistics.json")["s3"]["h1"]["z"]
    bird = by["bird"]
    meet = [(a, b) for a, b in itertools.combinations(SIX, 2) if pair_stats(bird, a, b, z)[1] >= .02]
    k, lb, _ = pair_stats(bird, "cypherturn", "tugraph", z)
    unf = [r for r in rows if all(r[s] == "0" for s in P7)]
    return {
        "prov.classes": dict(sorted(Counter(cls.values()).items())),
        "prov.join_complete": sorted(rid(r) for r in rows) == sorted(cls),
        "prov.nonunanimous_six": {"project": [non(by["project"]), len(by["project"])], "bird": [non(bird), len(bird)],
                                  "project_pct": f"{100 * non(by['project']) / len(by['project']):.1f}", "bird_pct": f"{100 * non(bird) / len(bird):.1f}"},
        "prov.bird_only_criterion": {"pairs_meeting": len(meet), "pairs": [f"{a}|{b}" for a, b in meet], "ct_tg_k": k, "ct_tg_lb_pct": f"{100 * lb:.2f}"},
        "prov.unanimous_reject_all_project": [sum(grp(r) == "project" for r in unf), len(unf)],
    }


# ------------------------------------------------------------------------------------------------ native suites
def native_claims(c):
    s18 = c.csv(S18R + "/s18_verdicts.csv"); s20 = c.csv(S20R + "/s20_verdicts.csv"); s23 = c.csv(S23R + "/s23_verdicts.csv")
    table = lambda rows: {k: {s: sum(r[s] == "1" for r in rows if r["class"] == k) for s in P7} | {"n": sum(r["class"] == k for r in rows),
                                                                                                   "cs_errors": sum(r["class"] == k and r["cyspider"].startswith("ERROR") for r in rows)}
                          for k in sorted({r["class"] for r in rows})}
    st23 = c.js(S23R + "/s23_statistics.json")
    sys.path.insert(0, c.p(S23 + "/code"))
    import s23_replication as REP
    pre = c.js(S23P + "/preregistration.json")
    ref = pre["reference_patterns"]["s20_by_class"]
    changed = total = 0
    for k, d in REP.S20_MAP.items():
        for s in P7:
            total += 1
            changed += REP.category([r[s] for r in s23 if r["class"] == k]) != ref[d][s]
    graphs = defaultdict(Counter)
    for r in s23: graphs[r["class"]][r["graph"]] += 1
    gen = c.js(S23 + "/candidates/generation_summary.json")
    d5 = [r for r in s20 if r["class"] == "D5_null_controlled"]
    return {
        "s18.n": len(s18),
        "s20.n": len(s20), "s20.table_SC": table(s20),
        "s20.null_class": {"n": len(d5), "unanimous": sum(len({r[s] for s in P7}) == 1 for r in d5), "gqlbench_rejects": sum(r["gqlbench"] == "0" for r in d5)},
        "s23.n": len(s23), "s23.graphs": len({r["graph"] for r in s23}), "s23.table_SC": table(s23),
        "s23.graph_by_class_SD": {k: dict(sorted(v.items())) for k, v in sorted(graphs.items())},
        "s23.covid_cases": sum(r["graph"] == "covid" for r in s23),
        "s23.list_cases_from_wwc": sum(r["graph"] == "wwc" for r in s23 if r["class"] == "R7_list_order"),
        "s23.eligible_sources": gen["eligible_distinct_sources"],
        "s23.replication": {k: v["status"] for k, v in sorted(st23["replication"].items())},
        "s23.decision": st23["study_decision_by_frozen_rule"]["decision"],
        "s23.shared_class_cells": {"cells": total, "changed_category": changed},
        "s23.statistics_match_verdicts": all(st23["by_class"][k]["per_scorer"][s]["accepted"] == v[s] for k, v in table(s23).items() for s in P7),
    }


def native_r2_claims(c):
    f = c.p(S23I + "/cases.jsonl")
    if not os.path.exists(f):
        cand = sorted(glob.glob(c.p("rebuild/s23/frozen/*_input/cases.jsonl")))
        if not cand: raise Boundary("needs Mind the Query cases: run scripts/full_native.sh s23 first")
        f = cand[-1]
    exp = {l.split()[1]: l.split()[0] for l in open(c.p(S23I + "/hashes.sha256"))}["cases.jsonl"]
    if hashlib.sha256(open(f, "rb").read()).hexdigest() != exp: raise Boundary("rebuilt Mind the Query cases.jsonl differs from the frozen hash")
    cases = [json.loads(l) for l in open(f)]
    return {"s23.multi_column_references": sum(len(x["reference"]["columns"]) >= 2 for x in cases)}


def study_hashes(root):
    """{repository-relative path: sha256} from every hashes.sha256 under experiments/ (entries are relative to the list's
    directory or to the repository root)."""
    out = {}
    for dp, _, fs in os.walk(os.path.join(root, "experiments")):
        if "hashes.sha256" not in fs: continue
        for line in open(os.path.join(dp, "hashes.sha256")):
            if not line.strip(): continue
            h, fn = line.split(None, 1); fn = fn.strip()
            for cand in (os.path.relpath(os.path.join(dp, fn), root), fn):
                if os.path.exists(os.path.join(root, cand)): out[os.path.normpath(cand)] = h
    return out


GROUPS = [("A", s1_claims), ("A", s3_claims), ("A", t2g_claims), ("A", s2_claims), ("A", native_claims),
          ("B", provenance_claims), ("B", None), ("R2", native_r2_claims)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=os.path.abspath(os.path.join(HERE, "..")), help="artifact root (default: this repository)")
    ap.add_argument("--dataset", default=os.environ.get("DATASET_DIR") or os.environ.get("CORPUS_PAIRS_DIR"),
                    help="root of the released dataset repository (layer B)")
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--require-all", action="store_true", help="fail unless every manifest claim was checked")
    ap.add_argument("--print-values", action="store_true", help="print computed values as JSON (no comparison)")
    a = ap.parse_args()
    c = Ctx(os.path.abspath(a.root), os.path.abspath(a.dataset) if a.dataset else None)
    got, boundary = {}, {}
    for layer, fn in GROUPS:
        try:
            got.update(model_level_claims(c, os.path.join(c.root, "rebuild", "model_level")) if fn is None else fn(c))
        except Boundary as e:
            boundary[(fn or model_level_claims).__name__] = str(e)
    if a.print_values:
        print(json.dumps(got, indent=1, sort_keys=True, default=list)); return
    man = json.load(open(a.manifest or os.path.join(HERE, "..", "expected_outputs", "paper_result_manifest.json")))
    # input integrity: dataset-repository inputs (released byte for byte) against the manifest SHA-256; inputs in this
    # repository against the per-study hashes.sha256 lists frozen with them (the same lists the legacy check verifies)
    hfail, unlisted, frozen_h = [], [], study_hashes(c.root)
    pf = c.p("provenance/public_file_provenance.csv")  # release file list (path, published SHA-256, ...); absent in the research tree
    prov_h = {r[0]: r[1] for r in csv.reader(open(pf)) if len(r) > 1} if os.path.exists(pf) else {}
    for rel, h in man["dataset_inputs"].items():
        f = os.path.join(c.dataset or "", rel)
        if c.dataset and os.path.exists(f) and hashlib.sha256(open(f, "rb").read()).hexdigest() != h: hfail.append("dataset:" + rel)
    for rel in sorted({i for e in man["claims"] for i in e["inputs"] if not i.startswith("dataset:") and not i.endswith("hashes.sha256")}):
        f = c.p(rel)
        h = frozen_h.get(rel) or prov_h.get(rel)
        if h is None: unlisted.append(rel); continue
        if hashlib.sha256(open(f, "rb").read()).hexdigest() != h: hfail.append(rel)
    fails, checked, skipped = [], 0, []
    for e in man["claims"]:
        cid = e["id"]
        if cid not in got:
            skipped.append(cid); print(f"[BOUNDARY] {cid} ({e['layer']}): not checkable here"); continue
        g = json.loads(json.dumps(got[cid], default=list))
        ok = g == e["expected"]; checked += 1
        print(f"[{'OK' if ok else 'FAIL'}] {cid} — {e['location']}" + ("" if ok else f"\n        got      {json.dumps(g)}\n        expected {json.dumps(e['expected'])}"))
        if not ok: fails.append(cid)
    for r in hfail: print(f"[FAIL] input hash {r}")
    for r in unlisted: print(f"[NOTE] input {r}: no frozen or release hash list covers it here; not verified")
    for k, v in boundary.items(): print(f"BOUNDARY {k}: {v}")
    total = len(man["claims"])
    status = "FAIL" if fails or hfail else ("PASS" if not skipped else "PARTIAL")
    print(f"\nPAPER CHECK: {status} — {checked}/{total} claims checked, {len(fails)} mismatches, {len(hfail)} input-hash mismatches, "
          f"{len(skipped)} not checkable here" + ("" if not skipped else " (layers needing the dataset repository or a native rebuild; see BOUNDARY)"))
    sys.exit(1 if fails or hfail or (a.require_all and skipped) else 0)


if __name__ == "__main__":
    main()
