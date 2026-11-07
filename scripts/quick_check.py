#!/usr/bin/env python3
"""LEGACY quick check (artifact-quick-v1), kept unchanged as a record. SUPERSEDED for the paper: its S1 lines check the ORIGINAL
controlled suite (e.g. CypherTurn 66/106), which the paper reports only as superseded; the paper-facing check is
scripts/paper_check.py (./reproduce.sh --quick). It recomputes the frozen-run numbers listed below from the
released frozen verdict files and compares them with the released frozen statistics. No Neo4j, no scorer, no
third-party download. Exit code 1 on any mismatch. Run from the artifact root:  python3 scripts/quick_check.py
Checks:
  0  every released file listed in a frozen hashes.sha256 matches its hash (withheld files are reported, not failed)
  S1 oracle agreement per scorer (106 oracle-defined fixtures) and the 9-fixture erratum list
  S3 21 pairwise disagreement counts, Bonferroni one-sided Wilson lower bounds, 11/21; 5/15 without CypherLens;
     six-scorer non-unanimity 41/563; unanimity 170 (161 pass, 9 fail)
  S2 informative subset: 37 predictions, 13 non-unanimous, per-scorer acceptances
  S18 / S20 / S23 accepted counts per class and scorer; S23 replication statuses re-derived with the frozen rubric
"""
import csv, hashlib, itertools, json, math, os, sys
sys.dont_write_bytecode = True  # never write .pyc into the artifact tree

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAIN_AUDIT = os.path.join(ROOT, "studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final")
P = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider"]
FAIL = []


def check(name, got, exp):
    ok = got == exp
    print(f"[{'OK' if ok else 'FAIL'}] {name}: {got}" + ("" if ok else f" (expected {exp})"))
    if not ok: FAIL.append(name)


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def hashes():
    present = withheld = 0
    for dp, _, fs in os.walk(os.path.join(ROOT, "studies")):
        if "hashes.sha256" not in fs: continue
        for line in open(os.path.join(dp, "hashes.sha256")):
            h, fn = line.split(None, 1); fn = fn.strip(); p = os.path.join(dp, fn)
            if not os.path.exists(p): withheld += 1; continue
            present += 1
            if sha(p) != h: FAIL.append(f"hash {os.path.relpath(p, ROOT)}"); print(f"[FAIL] hash {p}")
    print(f"[{'OK' if not any(f.startswith('hash') for f in FAIL) else 'FAIL'}] frozen hashes: {present} released files verified; {withheld} withheld files not present")


def wilson_lb(k, n, z):
    p = k / n; d = 1 + z * z / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d


def s1():
    st = json.load(open(os.path.join(MAIN_AUDIT, "audit_statistics.json")))["s1"]["per_scorer"]
    rows = list(csv.DictReader(open(os.path.join(MAIN_AUDIT, "s1_results.csv"))))
    for s in P:
        corr = sum(1 for r in rows if r["expected"] in ("EQUIV", "NONEQUIV")
                   and r[s] == ("1" if r["expected"] == "EQUIV" else "0"))
        check(f"S1 {s} correct/106", corr, st[s]["correct"])
    cases = [json.loads(l) for l in open(os.path.join(ROOT, "studies/controlled_suite/audit/s1/s1_cases.jsonl"))]
    err = sorted(c["case_id"] for c in cases if c["ref_query"] == c["pred_query"])
    exp = json.load(open(os.path.join(ROOT, "expected_outputs/s1_erratum.json")))["identical_query_text_fixtures"]
    check("S1 erratum fixtures (identical query text)", err, exp)


def s3():
    st = json.load(open(os.path.join(MAIN_AUDIT, "audit_statistics.json")))["s3"]
    z = st["h1"]["z"]
    rows = list(csv.DictReader(open(os.path.join(MAIN_AUDIT, "s3_results.csv"))))
    fro = {(r["scorer_a"], r["scorer_b"]): r for r in csv.DictReader(open(os.path.join(MAIN_AUDIT, "s3_pairwise_disagreement.csv")))}
    meets = meets_nocl = 0; bad = 0
    for a, b in itertools.combinations(P, 2):
        k = sum(r[a] != r[b] for r in rows); n = len(rows); lb = wilson_lb(k, n, z)
        f = fro.get((a, b)) or fro.get((b, a))
        if int(f["disagreements"]) != k or abs(float(f["lower_bonf_one_sided"]) - lb) > 1e-12: bad += 1
        meets += lb >= 0.02
        if "cypherlens" not in (a, b): meets_nocl += lb >= 0.02
    check("S3 pairwise counts and lower bounds match frozen table (mismatches)", bad, 0)
    check("S3 pairs meeting pre-specified criterion", meets, st["h1"]["n_pairs_meeting"])
    check("S3 pairs meeting without CypherLens (post-hoc)", meets_nocl, 5)
    six = [s for s in P if s != "cypherlens"]
    check("S3 six-scorer non-unanimous", sum(len({r[s] for s in six}) > 1 for r in rows), 41)
    un = [r for r in rows if len({r[s] for s in P}) == 1]
    check("S3 unanimous (pass, fail)", (sum(r["cypherturn"] == "1" for r in un), sum(r["cypherturn"] == "0" for r in un)),
          (st["unanimity"]["unanimous_pass"], st["unanimity"]["unanimous_fail"]))


def s2():
    d = os.path.join(ROOT, "studies/native_cypherturn_stress/native_equivalence_stress/frozen/20261030T143405Z_s2_sensitivity")
    res = json.load(open(os.path.join(d, "s2_sensitivity_results.json")))
    ids = set(res["informative_case_ids"])
    rows = [r for r in csv.DictReader(open(os.path.join(MAIN_AUDIT, "s2_results.csv"))) if r["case_id"] in ids]
    check("S2 informative N", len(rows), res["primary_informative_subset"]["N"])
    check("S2 non-unanimous", sum(len({r[s] for s in P}) > 1 for r in rows), res["primary_informative_subset"]["non_unanimous"])
    check("S2 per-scorer acceptances", {s: sum(r[s] == "1" for r in rows) for s in P},
          res["primary_informative_subset"]["per_scorer_accept"])


def native(label, csvp, statp, key):
    rows = list(csv.DictReader(open(os.path.join(ROOT, csvp))))
    st = json.load(open(os.path.join(ROOT, statp)))
    groups = {}
    for r in rows: groups.setdefault(r[key], []).append(r)
    bad = 0
    for g, rs in groups.items():
        ps = st["per_family"][g] if "per_family" in st and g in st["per_family"] else st["by_class"][g]["per_scorer"]
        for s in P:
            if sum(r[s] == "1" for r in rs) != ps[s]["accepted"]: bad += 1
    check(f"{label} accepted counts per class x scorer (mismatches over {len(groups)} classes)", bad, 0)
    return groups


def s23_rubric(groups):
    sys.path.insert(0, os.path.join(ROOT, "studies/native_mind_the_query/mind_the_query_replication/code"))
    import s23_replication as REP
    pre = json.load(open(os.path.join(ROOT, "studies/native_mind_the_query/mind_the_query_replication/frozen/20261031T175346Z_preregistration/preregistration.json")))
    st = json.load(open(os.path.join(ROOT, "studies/native_mind_the_query/mind_the_query_replication/frozen/20261031T181038Z_results/s23_statistics.json")))
    for k, rs in sorted(groups.items()):
        cats = {s: REP.category([r[s] for r in rs]) for s in P}
        if k in REP.S20_MAP:
            got = REP.classify(pre["reference_patterns"]["s20_by_class"][REP.S20_MAP[k]], cats, len(rs))[0]
            check(f"S23 {k} replication status", got, st["replication"][k]["status"])
    check("S23 session decision (frozen rule)", st["study_decision_by_frozen_rule"]["decision"],
          json.load(open(os.path.join(ROOT, "expected_outputs/expected_summary.json")))["s23_study_decision"])


def main():
    hashes(); s1(); s3(); s2()
    native("S18", "studies/native_cypherturn_validation/native_cypher/frozen/20261030T083338Z_native_cypher_results/s18_verdicts.csv",
           "studies/native_cypherturn_validation/native_cypher/frozen/20261030T083338Z_native_cypher_results/s18_statistics.json", "family")
    native("S20", "studies/native_cypherturn_stress/native_equivalence_stress/frozen/20261030T143804Z_results/s20_verdicts.csv",
           "studies/native_cypherturn_stress/native_equivalence_stress/frozen/20261030T143804Z_results/s20_statistics.json", "class")
    g = native("S23", "studies/native_mind_the_query/mind_the_query_replication/frozen/20261031T181038Z_results/s23_verdicts.csv",
               "studies/native_mind_the_query/mind_the_query_replication/frozen/20261031T181038Z_results/s23_statistics.json", "class")
    s23_rubric(g)
    print(f"\nQUICK: {'PASS' if not FAIL else 'FAIL'} ({len(FAIL)} failures)")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
