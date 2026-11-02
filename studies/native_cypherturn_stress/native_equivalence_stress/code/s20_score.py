#!/usr/bin/env python3
"""study S20 scoring + descriptive analysis (s20-score-v1). Runs ONLY on a frozen, hash-verified S20 input package.

Each of the 7 primary (+2 secondary, context only) scorers is invoked once per case through the FROZEN Study-14
runner (run_experiment_v1_1.py: frozen Study-13 adapters, hash-checked; network blocked; per-case 120 s limit).
No scorer logic is changed. Descriptive statistics only (post-freeze stress test; no confirmatory hypothesis; classes
are never pooled into one test): per class x scorer accept/reject with Wilson 95% CI; per-class pairwise
disagreement; per-class unanimity. Uses the study S18 `analyse` function unchanged.
  python s20_score.py <frozen_input_dir> <out_dir>
"""
import csv, hashlib, json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "studies", "native_cypherturn_validation", "native_cypher", "code"))
from s18_score import analyse, PRIMARY, SECONDARY, RUNNER  # frozen S18 analysis, reused unchanged


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def verify_freeze(fin):
    for l in open(os.path.join(fin, "hashes.sha256")):
        h, fn = l.split()
        assert sha(os.path.join(fin, fn)) == h, f"input freeze violated: {fn}"


def is_cypher(q): return bool(re.search(r"\bRETURN\b", q)) and not re.search(r"\bSELECT\b", q, re.I)


def main():
    fin, out = sys.argv[1], sys.argv[2]
    verify_freeze(fin)
    cases = [json.loads(l) for l in open(os.path.join(fin, "cases.jsonl"))]
    assert all(is_cypher(c["reference"]["query"]) and is_cypher(c["prediction"]["query"]) for c in cases), "non-Cypher side"
    os.makedirs(os.path.join(out, "raw"), exist_ok=False)
    cls = {c["case_id"]: c["meta"]["family"] for c in cases}
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="")
    verdicts = {c["case_id"]: {} for c in cases}
    log = {"runner": RUNNER, "runner_sha256": sha(RUNNER), "input_hashes_sha256": sha(os.path.join(fin, "hashes.sha256")),
           "runs": []}
    for s in PRIMARY + SECONDARY:
        rp = os.path.join(out, "raw", f"{s}.jsonl")
        p = subprocess.run([sys.executable, RUNNER, s, "s20", os.path.join(fin, "cases.jsonl"), rp],
                           capture_output=True, text=True, env=env, timeout=3600)
        if p.returncode != 0: raise SystemExit(f"runner failed for {s}: {p.stderr[-800:]}")
        os.chmod(rp, 0o444); log["runs"].append(p.stdout.strip().splitlines()[-1] if p.stdout.strip() else "")
        for l in open(rp):
            r = json.loads(l); verdicts[r["case_id"]][s] = r["verdict"]
    res = {"by_class": {}, "overall_descriptive_only": analyse(verdicts, cls)}
    for k in sorted(set(cls.values())):
        sub = {c: v for c, v in verdicts.items() if cls[c] == k}
        res["by_class"][k] = analyse(sub, {c: k for c in sub})
    json.dump(res, open(os.path.join(out, "s20_statistics.json"), "w"), indent=1)
    json.dump(log, open(os.path.join(out, "run_log.json"), "w"), indent=1)
    with open(os.path.join(out, "s20_verdicts.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["case_id", "class", "equivalence_class", "controlled_fixture"] + PRIMARY + SECONDARY)
        for c in cases:
            w.writerow([c["case_id"], cls[c["case_id"]], c["meta"]["equivalence_class"], c["meta"]["controlled_fixture"]]
                       + [verdicts[c["case_id"]][s] for s in PRIMARY + SECONDARY])
    lines = [f"{sha(os.path.join(dp, f))}  {os.path.relpath(os.path.join(dp, f), out)}"
             for dp, _, fs in sorted(os.walk(out)) for f in sorted(fs) if f != "hashes.sha256"]
    open(os.path.join(out, "hashes.sha256"), "w").write("\n".join(lines) + "\n")
    print(json.dumps({k: {s: v["per_scorer"][s]["accepted"] for s in PRIMARY} | {"n": v["unanimity"]["n_complete"]}
                      for k, v in res["by_class"].items()}, indent=1))


if __name__ == "__main__":
    main()
