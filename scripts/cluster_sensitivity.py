#!/usr/bin/env python3
"""POST-HOC, exploratory cluster-resampling sensitivity for the corpus pairwise test (supplement section S-G).

  python3 artifact_scripts/cluster_sensitivity.py DATASET_DIR

Not pre-specified. Inputs: the frozen corpus verdicts in this repository (s3_results.csv) and, from the dataset
repository, the per-record split file (provenance class) and the corpus records (gold SQL, used only to group records).
Records are grouped by the set of tables named after FROM/JOIN in their gold SQL. For the 15 pairs of the six in-domain
scorers, on all 563 records and on the 464 BIRD-derived records, it reports the pre-specified one-sided Wilson lower
bound (Bonferroni z = 2.8227), the two-sided 95% Wilson interval, and, over 50 seeds (1000..1049) of B = 10,000 cluster
resamples each, the median 0.05/21-quantile bound and the number of seeds in which it reaches 2%. Exit 1 if the
numbers differ from supplement S-G."""
import csv, itertools, json, math, os, re, sys
from statistics import NormalDist
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
S3 = os.path.join(ROOT, "studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final/s3_results.csv")
SIX = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cyspider"]
Z_BONF, Z95 = NormalDist().inv_cdf(1 - 0.05 / 21), NormalDist().inv_cdf(0.975)
# supplement S-G: pair -> (pairs meeting the protocol criterion, median cluster bound, seeds >= 2%) for the pairs it names
EXPECTED = {"all_563": {"meet": 5, "cypherturn|gqlbench": (0.02443, 50), "cypherturn|tugraph": (0.03178, 50),
                        "tugraph|pipecypher": (0.02086, 44), "cypherturn|cypherbench": (0.01713, 0), "tugraph|cyspider": (0.01496, 0)},
            "bird_derived_464": {"meet": 1, "cypherturn|tugraph": (0.02044, 38)}}


def wilson(k, n, z):
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - w), min(1.0, c + w)


def tables(sql):
    return tuple(sorted({t.lower() for t in re.findall(r'(?:FROM|JOIN)\s+[`"\[]?(\w+)', sql or "", re.I)})) or ("<none>",)


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else sys.exit("usage: cluster_sensitivity.py DATASET_DIR")
    rows = list(csv.DictReader(open(S3)))
    prov = {r["record_id"]: r["provenance_class"] for r in csv.DictReader(open(os.path.join(ds, "splits/record_splits.csv")))}
    sql = {json.loads(l)["s3_case_id"]: json.loads(l)["SQL"] for l in open(os.path.join(ds, "corpus/records_release_candidate.jsonl"), encoding="utf-8")}
    for r in rows:
        r["p"] = prov["WC-" + r["case_id"].split("-")[1]]; r["c"] = tables(sql[r["case_id"]])
    fails = 0
    for name, rs in (("all_563", rows), ("bird_derived_464", [r for r in rows if not r["p"].startswith("R-C")])):
        cl = sorted({r["c"] for r in rs}); ci = {c: j for j, c in enumerate(cl)}
        per = {}
        for a, b in itertools.combinations(SIX, 2):
            ck = np.zeros(len(cl)); cn = np.zeros(len(cl))
            for r in rs: cn[ci[r["c"]]] += 1; ck[ci[r["c"]]] += r[a] != r[b]
            per[f"{a}|{b}"] = (ck, cn, int(ck.sum()), int(cn.sum()))
        bounds = {p: [] for p in per}
        for seed in range(50):
            S = np.random.default_rng(1000 + seed).integers(0, len(cl), (10000, len(cl)))
            for p, (ck, cn, _, _) in per.items():
                bounds[p].append(float(np.quantile(ck[S].sum(1) / cn[S].sum(1), 0.05 / 21)))
        meet = 0
        print(f"{name}: {len(cl)} clusters")
        for p, (_, _, k, n) in per.items():
            lb, (lo, hi) = wilson(k, n, Z_BONF)[0], wilson(k, n, Z95); meet += lb >= 0.02
            med = float(np.median(bounds[p])); seeds = sum(x >= 0.02 for x in bounds[p])
            exp = EXPECTED[name].get(p); ok = exp is None or (abs(med - exp[0]) < 5e-6 and seeds == exp[1]); fails += not ok
            print(f"  [{'OK' if ok else 'FAIL'}] {p}: {k}/{n} Wilson LB {lb:.4f} 95% [{lo:.4f}, {hi:.4f}] cluster LB median {med:.5f}, >=2% in {seeds}/50")
        ok = meet == EXPECTED[name]["meet"]; fails += not ok
        print(f"  [{'OK' if ok else 'FAIL'}] pairs meeting the pre-specified criterion: {meet}/15")
    print("CLUSTER SENSITIVITY:", "PASS" if not fails else "FAIL")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
