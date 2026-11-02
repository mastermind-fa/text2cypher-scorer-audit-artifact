#!/usr/bin/env python3
"""study S18 scoring + descriptive analysis (s18-score-v1). Runs ONLY on a frozen S18 input package.

Each of the 7 primary (+2 secondary) scorers is invoked through the FROZEN Study-14 runner
(studies/corpus_audit/audit_analysis/code/run_experiment_v1_1.py: frozen Study-13 adapters, hash-checked; network
blocked; per-case 120 s limit), once per case. All admitted cases are oracle-equivalent, so a pass = agreement with
the oracle. Descriptive statistics only (post-freeze validation; no confirmatory hypothesis):
per scorer x family acceptance with Wilson 95% CI; pairwise disagreement; unanimity.
  python s18_score.py <frozen_input_dir> <out_dir>
"""
import csv, hashlib, itertools, json, os, subprocess, sys
from statistics import NormalDist
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
RUNNER = os.path.join(ROOT, "studies", "corpus_audit", "audit_analysis", "code", "run_experiment_v1_1.py")
PRIMARY = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider"]
SECONDARY = ["neo4jlabs", "pc_v1_1"]
Z = NormalDist().inv_cdf(0.975)

def wilson(k, n):
    if not n: return [None, None]
    p = k / n; d = 1 + Z * Z / n; c = (p + Z * Z / (2 * n)) / d
    h = Z * ((p * (1 - p) / n + Z * Z / (4 * n * n)) ** 0.5) / d
    return [max(0.0, c - h), min(1.0, c + h)]

def ok(v): return isinstance(v, (int, float, bool)) and v in (0, 1)

def analyse(verdicts, fam):
    out = {"per_scorer": {}, "per_family": {}, "pairwise": [], "unanimity": {}}
    for s in PRIMARY + SECONDARY:
        vals = [verdicts[c][s] for c in verdicts]
        k = sum(1 for v in vals if ok(v) and int(v) == 1); n = sum(1 for v in vals if ok(v))
        out["per_scorer"][s] = {"n": n, "accepted": k, "rejected": n - k, "errors": len(vals) - n,
                                "acceptance": k / n if n else None, "wilson95": wilson(k, n)}
        for f in sorted(set(fam.values())):
            fv = [verdicts[c][s] for c in verdicts if fam[c] == f]
            fk = sum(1 for v in fv if ok(v) and int(v) == 1); fn = sum(1 for v in fv if ok(v))
            out["per_family"].setdefault(f, {})[s] = {"n": fn, "accepted": fk, "errors": len(fv) - fn,
                                                      "acceptance": fk / fn if fn else None, "wilson95": wilson(fk, fn)}
    for a, b in itertools.combinations(PRIMARY, 2):
        both = [c for c in verdicts if ok(verdicts[c][a]) and ok(verdicts[c][b])]
        k = sum(int(verdicts[c][a]) != int(verdicts[c][b]) for c in both)
        out["pairwise"].append({"a": a, "b": b, "n": len(both), "disagreements": k,
                                "rate": k / len(both) if both else None, "wilson95": wilson(k, len(both))})
    comp = [c for c in verdicts if all(ok(verdicts[c][s]) for s in PRIMARY)]
    un = sum(len({int(verdicts[c][s]) for s in PRIMARY}) == 1 for c in comp)
    out["unanimity"] = {"n_complete": len(comp), "unanimous": un, "non_unanimous": len(comp) - un,
                        "all_accept": sum(all(int(verdicts[c][s]) == 1 for s in PRIMARY) for c in comp)}
    return out

def main():
    fin, out = sys.argv[1], sys.argv[2]
    for l in open(os.path.join(fin, "hashes.sha256")):
        h, fn = l.split()
        assert hashlib.sha256(open(os.path.join(fin, fn), "rb").read()).hexdigest() == h, f"input freeze violated: {fn}"
    os.makedirs(os.path.join(out, "raw"), exist_ok=False)
    cases = [json.loads(l) for l in open(os.path.join(fin, "cases.jsonl"))]
    fam = {c["case_id"]: c["meta"]["family"] for c in cases}
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="")
    verdicts = {c["case_id"]: {} for c in cases}
    for s in PRIMARY + SECONDARY:
        rp = os.path.join(out, "raw", f"{s}.jsonl")
        p = subprocess.run([sys.executable, RUNNER, s, "s18", os.path.join(fin, "cases.jsonl"), rp],
                           capture_output=True, text=True, env=env, timeout=3600)
        if p.returncode != 0: raise SystemExit(f"runner failed for {s}: {p.stderr[-800:]}")
        os.chmod(rp, 0o444)
        for l in open(rp):
            r = json.loads(l); verdicts[r["case_id"]][s] = r["verdict"]
    res = analyse(verdicts, fam)
    json.dump(res, open(os.path.join(out, "s18_statistics.json"), "w"), indent=1)
    with open(os.path.join(out, "s18_verdicts.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["case_id", "family"] + PRIMARY + SECONDARY)
        for c in cases: w.writerow([c["case_id"], fam[c["case_id"]]] + [verdicts[c["case_id"]][s] for s in PRIMARY + SECONDARY])
    lines = [f"{hashlib.sha256(open(os.path.join(dp, f), 'rb').read()).hexdigest()}  {os.path.relpath(os.path.join(dp, f), out)}"
             for dp, _, fs in sorted(os.walk(out)) for f in sorted(fs) if f != "hashes.sha256"]
    open(os.path.join(out, "hashes.sha256"), "w").write("\n".join(lines) + "\n")
    print(json.dumps({"unanimity": res["unanimity"], "acceptance": {s: v["acceptance"] for s, v in res["per_scorer"].items()}}))

if __name__ == "__main__":
    main()
