#!/usr/bin/env python3
"""study S20 secondary analysis: prediction-level verdict sensitivity on the FROZEN S2 set (s20-s2-v1).
Reads only the frozen the main audit run result (s2_results.csv, hash-checked against the S14 freeze manifest). No scorer is
re-run, no prediction is generated, no ranking or leaderboard quantity is computed.

  step 1:  python s2_sensitivity.py define <out_dir>    -> writes + hashes the subset definition (before any metric)
  step 2:  python s2_sensitivity.py compute <out_dir>   -> verifies the definition hash, computes, freezes results
"""
import csv, datetime, hashlib, json, os, sys
from statistics import NormalDist
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
S14 = os.path.join(ROOT, "studies", "corpus_audit", "audit_final", "frozen", "20261029T190431Z_audit_final")
PRIMARY = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider"]
Z = NormalDist().inv_cdf(0.975)

DEFINITION = {
    "analysis": "prediction-level verdict sensitivity (NOT ranking / leaderboard impact)",
    "source": "studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final/s2_results.csv (frozen S14)",
    "primary_informative_subset": "rows with empty_prediction == False AND a binary (0/1) verdict from all seven primary "
                                  "scorers",
    "justification": [
        "empty predictions (117/158) are dominated by an output-floor effect and mostly fail every scorer trivially;",
        "rows with a scorer exception (CySpider TypeError on list/map values) have no complete seven-scorer verdict "
        "vector, so non-unanimity is undefined for them;",
        "the rule uses only columns frozen in the main audit run and was written before any study S20 metric was computed."],
    "context_sets_reported_separately": ["all 158 rows (counts only)", "all rows with seven binary verdicts (154)"],
    "metrics": ["N", "unanimous / non-unanimous (Wilson 95%)", "accepted by >= 1 scorer", "rejected by >= 1 scorer",
                "per-scorer accept count", "max - min per-scorer acceptance rate on the same subset (with and without "
                "CypherLens)", "strict-majority (>= 4 of 7) verdict vs each scorer", "sole-accept / sole-reject counts"],
}


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def wilson(k, n):
    if not n: return [None, None]
    p = k / n; d = 1 + Z * Z / n; c = (p + Z * Z / (2 * n)) / d
    h = Z * ((p * (1 - p) / n + Z * Z / (4 * n * n)) ** 0.5) / d
    return [max(0.0, c - h), min(1.0, c + h)]


def frozen_s2():
    src = os.path.join(S14, "s2_results.csv")
    manifest = {l.split()[1]: l.split()[0] for l in open(os.path.join(S14, "hashes.sha256")) if l.strip()}
    assert manifest.get("s2_results.csv") == sha(src), "S14 s2_results.csv does not match its freeze manifest"
    return list(csv.DictReader(open(src))), sha(src)


def binary(v): return v in ("0", "1")


def summarise(rows):
    n = len(rows); V = [[int(r[s]) for s in PRIMARY] for r in rows]
    acc = {s: sum(v[i] for v in V) for i, s in enumerate(PRIMARY)}
    un = sum(len(set(v)) == 1 for v in V)
    rate = {s: acc[s] / n for s in PRIMARY} if n else {}
    six = [s for s in PRIMARY if s != "cypherlens"]
    maj = [int(sum(v) >= 4) for v in V]
    out = {"N": n, "unanimous": un, "non_unanimous": n - un,
           "non_unanimous_fraction": (n - un) / n if n else None, "non_unanimous_wilson95": wilson(n - un, n),
           "unanimous_accept": sum(all(v) for v in V), "unanimous_reject": sum(not any(v) for v in V),
           "accepted_by_at_least_one": sum(any(v) for v in V), "rejected_by_at_least_one": sum(not all(v) for v in V),
           "per_scorer_accept": acc, "per_scorer_accept_rate": rate,
           "max_scorer_induced_acceptance_difference": (max(rate.values()) - min(rate.values())) if n else None,
           "max_scorer_induced_acceptance_difference_excl_cypherlens":
               (max(rate[s] for s in six) - min(rate[s] for s in six)) if n else None,
           "majority_accept": sum(maj),
           "disagreements_with_majority": {s: sum(v[i] != m for v, m in zip(V, maj)) for i, s in enumerate(PRIMARY)},
           "sole_accept": {s: sum(v[i] == 1 and sum(v) == 1 for v in V) for i, s in enumerate(PRIMARY)},
           "sole_reject": {s: sum(v[i] == 0 and sum(v) == 6 for v in V) for i, s in enumerate(PRIMARY)}}
    six_V = [[v[i] for i, s in enumerate(PRIMARY) if s != "cypherlens"] for v in V]
    out["non_unanimous_excl_cypherlens"] = sum(len(set(v)) > 1 for v in six_V)
    return out


def main():
    step, out = sys.argv[1], sys.argv[2]
    dpath = os.path.join(out, "s2_subset_definition.json")
    if step == "define":
        os.makedirs(out, exist_ok=False)
        _, src_sha = frozen_s2()
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json.dump({**DEFINITION, "source_sha256": src_sha, "script_sha256": sha(os.path.abspath(__file__)),
                   "defined_utc": stamp, "status": "DEFINED BEFORE ANY STUDY S20 S2 METRIC"}, open(dpath, "w"), indent=2)
        open(os.path.join(out, "definition.sha256"), "w").write(f"{sha(dpath)}  s2_subset_definition.json\n")
        print(json.dumps({"defined": dpath, "sha256": sha(dpath)})); return
    h = open(os.path.join(out, "definition.sha256")).read().split()[0]
    assert sha(dpath) == h, "definition changed after freeze"
    d = json.load(open(dpath))
    assert d["script_sha256"] == sha(os.path.abspath(__file__)), "analysis script changed after the definition freeze"
    rows, _ = frozen_s2()
    empty = [r for r in rows if r["empty_prediction"] == "True"]
    nonempty = [r for r in rows if r["empty_prediction"] == "False"]
    complete = [r for r in rows if all(binary(r[s]) for s in PRIMARY)]
    informative = [r for r in nonempty if all(binary(r[s]) for s in PRIMARY)]
    res = {"counts": {"all": len(rows), "empty_predictions": len(empty), "nonempty_predictions": len(nonempty),
                      "complete_seven_verdicts": len(complete), "with_scorer_error": len(rows) - len(complete),
                      "scorer_errors": {s: sum(not binary(r[s]) for r in rows) for s in PRIMARY},
                      "nonempty_with_scorer_error": len(nonempty) - len(informative)},
           "primary_informative_subset": summarise(informative),
           "context_all_complete": summarise(complete),
           "informative_case_ids": [r["case_id"] for r in informative],
           "per_model_informative": {m: summarise([r for r in informative if r["model"] == m])
                                     for m in sorted({r["model"] for r in informative})},
           "definition_sha256": h, "computed_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")}
    json.dump(res, open(os.path.join(out, "s2_sensitivity_results.json"), "w"), indent=1)
    lines = [f"{sha(os.path.join(out, f))}  {f}" for f in sorted(os.listdir(out)) if f != "hashes.sha256"]
    open(os.path.join(out, "hashes.sha256"), "w").write("\n".join(lines) + "\n")
    print(json.dumps({"counts": res["counts"], "informative": {k: v for k, v in res["primary_informative_subset"].items()
                      if k not in ("per_scorer_accept_rate",)}}, indent=1))


if __name__ == "__main__":
    main()
