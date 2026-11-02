#!/usr/bin/env python3
"""Verdict-level comparison of a rebuilt native-Cypher run with the frozen one (reproduction check).
  python3 scripts/compare_verdicts.py <frozen_verdicts.csv> <rebuilt_verdicts.csv> <class_column>
Reports two levels, and never edits expected outputs:
  STRICT   : per-class accepted counts identical for all 7 primary scorers, and identical verdicts on common cases
  CATEGORY : every scorer has the same per-class category (all accept / all reject / mixed / error) in both runs,
             and identical verdicts on every case present in both runs
Exit 0 iff CATEGORY holds (STRICT is reported). CypherTurn graphs are loaded by Cypher CREATE statements; Neo4j
internal-ID reuse across loads can change unordered row sequences, ORDER BY ... LIMIT tie-breaks, and floating-point
summation order, so the oracle may admit a slightly different set of cases (the fresh-environment reproduction report §5)."""
import collections, csv, json, sys
P = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider"]
fz, rb, col = sys.argv[1:4]
F = {r["case_id"]: r for r in csv.DictReader(open(fz))}; R = {r["case_id"]: r for r in csv.DictReader(open(rb))}
def agg(D):
    a = collections.defaultdict(collections.Counter)
    for r in D.values():
        a[r[col]]["n"] += 1
        for s in P: a[r[col]][s] += r[s] == "1"
    return {k: dict(v) for k, v in a.items()}
def cat(D):
    out = {}
    for k in {r[col] for r in D.values()}:
        rs = [r for r in D.values() if r[col] == k]
        for s in P:
            v = {r[s] for r in rs}
            out[(k, s)] = "ACCEPT" if v == {"1"} else "REJECT" if v == {"0"} else "ERROR" if all(x.startswith("ERROR") for x in v) else "MIXED"
    return out
common = set(F) & set(R); diff = [c for c in common if any(F[c][s] != R[c][s] for s in P)]
fa, ra = agg(F), agg(R)
count_diffs = {k: {"frozen": fa.get(k), "rebuilt": ra.get(k)} for k in set(fa) | set(ra) if fa.get(k) != ra.get(k)}
strict = not count_diffs and not diff
category = cat(F) == cat(R) and not diff
res = {"frozen_cases": len(F), "rebuilt_cases": len(R), "common_cases": len(common), "only_frozen": sorted(set(F) - set(R)),
       "only_rebuilt": sorted(set(R) - set(F)), "per_case_verdict_differences": len(diff),
       "per_class_count_differences": count_diffs, "STRICT": strict, "CATEGORY": category}
print(json.dumps(res))
print(("OK   " if category else "FAIL ") + f"verdict-level reproduction (CATEGORY={category}, STRICT={strict})")
sys.exit(0 if category else 1)
