#!/usr/bin/env python3
"""Execute the frozen MAIN_AUDIT experiment once: S1 -> S3 -> S2, all 9 scorers (audit-run-all-v1).

  python run_all.py <final_dir>     # final_dir contains pairs/ (from build_pairs.py); writes raw/ there

Refuses to run unless ANALYSIS_FREEZE.json exists and every listed file hash matches (code frozen before execution),
and refuses to overwrite an existing raw/ directory (each set runs once).
Retry rule (pre-declared): if a scorer PROCESS fails (non-zero exit or missing/short output), that scorer's whole set
is rerun once and the failure is logged in raw/run_log.json. Per-case scorer exceptions are results, never retried.
Raw files are made read-only (0444) immediately after writing.
"""
import hashlib
import json
import os
import subprocess
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
S1 = os.path.join(ROOT, "studies", "controlled_suite", "audit", "s1", "s1_cases.jsonl")
S1_SHA = "80d0fd3fa181470fb5d59c0fbeea9cf748e1cd2bcc3ade61e4387118a17d5b47"
FREEZE = os.path.join(HERE, "..", "ANALYSIS_FREEZE.json")
SCORERS = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider",
           "neo4jlabs", "pc_v1_1"]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def check_freeze():
    fz = json.load(open(FREEZE))
    for rel, h in fz["files_sha256"].items():
        if sha(os.path.join(HERE, "..", rel)) != h:
            raise SystemExit(f"analysis freeze violated: {rel}")
    return fz


def nlines(p):
    return sum(1 for _ in open(p))


def main():
    final = sys.argv[1]
    fz = check_freeze()
    if sha(S1) != S1_SHA:
        raise SystemExit("S1 hash mismatch")
    raw = os.path.join(final, "raw")
    if os.path.exists(raw):
        raise SystemExit("raw/ already exists: each set runs once")
    os.makedirs(raw)
    inputs = {"s1": S1, "s3": os.path.join(final, "pairs", "s3_pairs.jsonl"),
              "s2": os.path.join(final, "pairs", "s2_pairs.jsonl")}
    log = {"started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "analysis_freeze": fz["freeze_sha256"],
           "order": ["s1", "s3", "s2"], "runs": [], "retries": []}
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="")
    for set_name in ["s1", "s3", "s2"]:
        os.makedirs(os.path.join(raw, set_name))
        expected = nlines(inputs[set_name])
        for scorer in SCORERS:
            out = os.path.join(raw, set_name, f"{scorer}.jsonl")
            for attempt in (1, 2):
                p = subprocess.run([sys.executable, os.path.join(HERE, "run_experiment.py"), scorer, set_name,
                                    inputs[set_name], out], capture_output=True, text=True, env=env, timeout=3600)
                ok = p.returncode == 0 and os.path.exists(out) and nlines(out) == expected
                if ok:
                    break
                log["retries"].append({"set": set_name, "scorer": scorer, "attempt": attempt,
                                       "returncode": p.returncode, "stderr_tail": p.stderr[-1500:]})
                if os.path.exists(out):
                    os.remove(out)
            if not ok:
                raise SystemExit(f"infrastructure failure after retry: {set_name}/{scorer}")
            os.chmod(out, 0o444)
            log["runs"].append({"set": set_name, "scorer": scorer, "n": expected, "sha256": sha(out),
                                "stdout": p.stdout.strip()[-400:], "stderr_tail": p.stderr[-400:]})
    log["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lp = os.path.join(raw, "run_log.json")
    json.dump(log, open(lp, "w"), indent=1)
    os.chmod(lp, 0o444)
    print(json.dumps({"runs": len(log["runs"]), "retries": len(log["retries"])}))


if __name__ == "__main__":
    main()
