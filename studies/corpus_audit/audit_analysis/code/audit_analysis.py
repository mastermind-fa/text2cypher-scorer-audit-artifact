"""MAIN_AUDIT statistics (audit-analysis-v1). Implements protocol audit-protocol-v1 §P7 exactly; frozen before any S1/S2/S3 run.

Verdict values per (unit, scorer): 1, 0, or "ERROR:<ExceptionClass>".
Primary (S3): for each of the 21 unordered pairs of the 7 PRIMARY scorers,
  D_ij = #units with v_i != v_j / #units where BOTH returned 0/1 (ERROR excluded from that pair's denominator).
  H1 (protocol name; Study-14 brief calls it H2): SUPPORTED iff any pair's one-sided Wilson lower bound at
  z = Phi^-1(1 - 0.05/21) is >= 0.02 (unrounded comparison).
Secondary: two-sided Wilson 95% per pair; unanimity; exact McNemar per pair (+ Bonferroni over 21); marginal pass
rates; ERROR->0 sensitivity; S2 question-clustered bootstrap (B=10000, seed 42); S1 oracle conformance on
EQUIV/NONEQUIV only (INTENT_DEPENDENT = policy profile only); deterministic disagreement features.
"""
import itertools
import math
import random
from statistics import NormalDist

PRIMARY = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider"]
SECONDARY = ["neo4jlabs", "pc_v1_1"]
H_THRESHOLD = 0.02
FAMILY_ALPHA = 0.05
N_HYPOTHESES = 21
PER_COMPARISON_ALPHA = FAMILY_ALPHA / N_HYPOTHESES
Z_BONF_ONE_SIDED = NormalDist().inv_cdf(1 - PER_COMPARISON_ALPHA)  # 2.8227...
Z_95_TWO_SIDED = NormalDist().inv_cdf(0.975)
BOOT_B, BOOT_SEED = 10000, 42


def is_binary(v):
    """True for 0/1 verdicts (int, float or bool); False for 'ERROR:...' strings and None."""
    return isinstance(v, (bool, int, float)) and v in (0, 1)


def wilson(k, n, z):
    """Wilson score interval (lo, hi) for k/n at normal quantile z. n == 0 -> (None, None)."""
    if n == 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def wilson_lower_one_sided(k, n, z=Z_BONF_ONE_SIDED):
    return wilson(k, n, z)[0]


def exact_mcnemar(b, c):
    """Two-sided exact McNemar p-value = binomial test of min(b,c) with n=b+c, p=0.5."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def pairs_of(scorers):
    return list(itertools.combinations(scorers, 2))


def pairwise(verdicts, scorers=PRIMARY, error_as_zero=False):
    """verdicts: {unit_id: {scorer: verdict}} -> list of per-pair dicts."""
    out = []
    for a, b in pairs_of(scorers):
        n = k = b10 = b01 = 0
        n_err = 0
        for u, v in verdicts.items():
            va, vb = v[a], v[b]
            if error_as_zero:
                va = 0 if not is_binary(va) else int(va)
                vb = 0 if not is_binary(vb) else int(vb)
            if not (is_binary(va) and is_binary(vb)):
                n_err += 1
                continue
            va, vb = int(va), int(vb)
            n += 1
            if va != vb:
                k += 1
                if va == 1:
                    b10 += 1
                else:
                    b01 += 1
        lo95, hi95 = wilson(k, n, Z_95_TWO_SIDED)
        p = exact_mcnemar(b10, b01)
        out.append({"scorer_a": a, "scorer_b": b, "n": n, "excluded_error": n_err, "disagreements": k,
                    "rate": (k / n) if n else None,
                    "lower_bonf_one_sided": wilson_lower_one_sided(k, n),
                    "wilson95_lo": lo95, "wilson95_hi": hi95,
                    "a1_b0": b10, "a0_b1": b01, "mcnemar_p": p, "mcnemar_p_bonf": min(1.0, p * N_HYPOTHESES)})
    return out


def h1_decision(pair_rows, threshold=H_THRESHOLD):
    lbs = [r["lower_bonf_one_sided"] for r in pair_rows if r["lower_bonf_one_sided"] is not None]
    best = max(pair_rows, key=lambda r: (r["lower_bonf_one_sided"] or -1))
    supported = any(lb >= threshold for lb in lbs)
    return {"supported": supported, "n_pairs": len(pair_rows), "n_pairs_meeting": sum(lb >= threshold for lb in lbs),
            "max_lower_bound": best["lower_bonf_one_sided"], "max_lower_pair": [best["scorer_a"], best["scorer_b"]],
            "max_rate": max((r["rate"] or 0) for r in pair_rows),
            "max_rate_pair": next([r["scorer_a"], r["scorer_b"]] for r in pair_rows
                                  if (r["rate"] or 0) == max((x["rate"] or 0) for x in pair_rows)),
            "threshold": threshold, "z": Z_BONF_ONE_SIDED, "family_alpha": FAMILY_ALPHA,
            "per_comparison_alpha": PER_COMPARISON_ALPHA, "n_hypotheses": N_HYPOTHESES,
            "one_sided_confidence": 1 - PER_COMPARISON_ALPHA}


def unanimity(verdicts, scorers=PRIMARY):
    complete = {u: v for u, v in verdicts.items() if all(is_binary(v[s]) for s in scorers)}
    groups = {u: len({int(v[s]) for s in scorers}) for u, v in complete.items()}
    unan = sum(g == 1 for g in groups.values())
    n = len(complete)
    lo, hi = wilson(unan, n, Z_95_TWO_SIDED)
    return {"n_complete": n, "n_with_error": len(verdicts) - n, "unanimous": unan,
            "at_least_one_disagreement": n - unan, "two_verdict_groups": sum(g >= 2 for g in groups.values()),
            "unanimity_rate": unan / n if n else None, "wilson95": [lo, hi],
            "unanimous_pass": sum(1 for u in complete if groups[u] == 1 and int(complete[u][scorers[0]]) == 1),
            "unanimous_fail": sum(1 for u in complete if groups[u] == 1 and int(complete[u][scorers[0]]) == 0)}


def marginals(verdicts, scorers):
    out = {}
    for s in scorers:
        vals = [v[s] for v in verdicts.values()]
        ok = [int(x) for x in vals if is_binary(x)]
        lo, hi = wilson(sum(ok), len(ok), Z_95_TWO_SIDED)
        out[s] = {"n": len(ok), "pass": sum(ok), "pass_rate": sum(ok) / len(ok) if ok else None,
                  "wilson95": [lo, hi], "errors": len(vals) - len(ok),
                  "error_classes": sorted({x for x in vals if not is_binary(x)})}
    return out


def cluster_bootstrap_pairwise(verdicts, clusters, scorers=PRIMARY, B=BOOT_B, seed=BOOT_SEED):
    """Question-clustered percentile bootstrap 95% CI of D_ij (S2). clusters: {unit_id: cluster_id}."""
    by_c = {}
    for u in verdicts:
        by_c.setdefault(clusters[u], []).append(u)
    cids = sorted(by_c)
    rng = random.Random(seed)
    reps = {p: [] for p in pairs_of(scorers)}
    for _ in range(B):
        draw = [rng.choice(cids) for _ in cids]
        for a, b in reps:
            n = k = 0
            for c in draw:
                for u in by_c[c]:
                    va, vb = verdicts[u][a], verdicts[u][b]
                    if is_binary(va) and is_binary(vb):
                        n += 1
                        k += int(va) != int(vb)
            if n:
                reps[(a, b)].append(k / n)
    out = {}
    for p, r in reps.items():
        r.sort()
        out[p] = (r[int(0.025 * len(r))], r[min(len(r) - 1, int(0.975 * len(r)))]) if r else (None, None)
    return out


def s1_oracle(verdicts, cases, scorers):
    """cases: {case_id: {"expected", "dimension"}}. EQUIV->1 correct, NONEQUIV->0 correct; INTENT_DEPENDENT excluded
    from accuracy (policy profile only). ERROR on an oracle-defined case counts as incorrect AND is reported."""
    per_scorer, per_dim, intent = {}, {}, {}
    for s in scorers:
        c = i = e = 0
        acc_eq = rej_ne = n_eq = n_ne = 0
        for cid, meta in cases.items():
            v = verdicts[cid][s]
            if meta["expected"] == "INTENT_DEPENDENT":
                intent.setdefault(s, {}).setdefault(meta["dimension"], []).append(v if is_binary(v) else "ERROR")
                continue
            want = 1 if meta["expected"] == "EQUIV" else 0
            ok = is_binary(v) and int(v) == want
            if not is_binary(v):
                e += 1
            c += ok
            i += not ok
            if want == 1:
                n_eq += 1
                acc_eq += ok
            else:
                n_ne += 1
                rej_ne += ok
            d = per_dim.setdefault(meta["dimension"], {}).setdefault(s, {"n": 0, "correct": 0, "incorrect": 0,
                                                                         "errors": 0, "verdicts": []})
            d["n"] += 1
            d["correct"] += ok
            d["incorrect"] += not ok
            d["errors"] += not is_binary(v)
            d["verdicts"].append(v if is_binary(v) else "ERROR")
        n = c + i
        lo, hi = wilson(c, n, Z_95_TWO_SIDED)
        per_scorer[s] = {"n_oracle_defined": n, "correct": c, "incorrect": i, "errors": e,
                         "oracle_agreement": c / n if n else None, "wilson95": [lo, hi],
                         "equiv_accept": acc_eq, "n_equiv": n_eq, "nonequiv_reject": rej_ne, "n_nonequiv": n_ne}
    return per_scorer, per_dim, intent


# ----------------------------------------------------------------- deterministic disagreement features (§P7 #5)
def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def features(pair):
    """Pre-declared mechanical features of a result pair (not causes). Returns sorted list of feature names."""
    r, p = pair["reference"], pair["prediction"]
    f = set()
    if r["columns"] != p["columns"] and r["rows"] and p["rows"]:
        f.add("key_name_difference")
    if "order by" in r["query"].lower():
        f.add("order_by_in_reference")
    if "order by" in p["query"].lower():
        f.add("order_by_in_prediction")
    if not r["rows"] or not p["rows"]:
        f.add("empty_side")
    rr, pr = [repr(x) for x in r["rows"]], [repr(x) for x in p["rows"]]
    if sorted(rr) == sorted(pr) and rr != pr:
        f.add("row_order_difference")
    if set(rr) == set(pr) and sorted(rr) != sorted(pr):
        f.add("multiplicity_difference")
    cells_r = [v for row in r["rows"] for v in row]
    cells_p = [v for row in p["rows"] for v in row]
    if any(v is None for v in cells_r + cells_p):
        f.add("null_present")
    if any(isinstance(v, (list, dict)) for v in cells_r + cells_p):
        f.add("list_or_map_cells")
    if len(r["rows"]) == len(p["rows"]) and r["rows"] and len(r["rows"][0]) == len(p["rows"][0]):
        sr = sorted(r["rows"], key=repr)
        sp = sorted(p["rows"], key=repr)
        for ra, pa in zip(sr, sp):
            for a, b in zip(ra, pa):
                if _num(a) and _num(b):
                    if type(a) is not type(b) and a == b:
                        f.add("int_float_type_difference")
                    elif isinstance(a, float) or isinstance(b, float):
                        if a != b and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12):
                            f.add("float_only_tiny_difference")
                elif (_num(a) and isinstance(b, str)) or (_num(b) and isinstance(a, str)):
                    f.add("number_string_type_difference")
    if len(r["rows"]) == len(p["rows"]) and r["rows"] and r["rows"][0] and p["rows"][0] \
            and len(r["rows"][0]) != len(p["rows"][0]):
        f.add("column_count_difference")
    return sorted(f)
