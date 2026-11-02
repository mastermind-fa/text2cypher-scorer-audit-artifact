#!/usr/bin/env python3
"""Resume the single MAIN_AUDIT execution after the infrastructure stall (audit-resume-v1). Pre-declared before use:

- Keep untouched every COMPLETE, read-only raw file written by run_all.py v1 (S1: 9 scorers; S3: 7 primary scorers).
- Delete the PARTIAL, never-sealed raw/s3/neo4jlabs.jsonl (process killed mid-set; never analysed) and rerun
  neo4j-labs' WHOLE S3 set once (retry rule), then pc_v1_1 S3 (never started), then S2 for all 9 scorers in the frozen
  scorer order, all with runner v1.1 (per-case 120 s timeout -> ERROR:CaseTimeout).
- Same isolation/env as run_all.py; outputs chmod 0444; refuses to overwrite any existing complete file.
"""
import datetime
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_all as RA  # noqa: E402


def main():
    final = sys.argv[1]
    fz = json.load(open(os.path.join(HERE, "..", "ANALYSIS_FREEZE_AMENDMENT_1.json")))
    for rel, h in fz["files_sha256"].items():
        if RA.sha(os.path.join(HERE, "..", rel)) != h:
            raise SystemExit(f"amended freeze violated: {rel}")
    raw = os.path.join(final, "raw")
    inputs = {"s1": RA.S1, "s3": os.path.join(final, "pairs", "s3_pairs.jsonl"),
              "s2": os.path.join(final, "pairs", "s2_pairs.jsonl")}
    log = {"started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "runner": "v1.1",
           "kept_v1_files": {}, "discarded_partial": [], "runs": [], "retries": []}
    for set_name, scorers in [("s1", RA.SCORERS), ("s3", RA.SCORERS[:7])]:
        for s in scorers:
            p = os.path.join(raw, set_name, f"{s}.jsonl")
            assert RA.nlines(p) == RA.nlines(inputs[set_name]) and not os.access(p, os.W_OK), p
            log["kept_v1_files"][f"{set_name}/{s}"] = RA.sha(p)
    partial = os.path.join(raw, "s3", "neo4jlabs.jsonl")
    if os.path.exists(partial):
        log["discarded_partial"].append({"file": "s3/neo4jlabs.jsonl", "lines": RA.nlines(partial),
                                         "reason": "process killed mid-set after O(n^2) stall; never sealed or analysed"})
        os.remove(partial)
    todo = [("s3", "neo4jlabs"), ("s3", "pc_v1_1")] + [("s2", s) for s in RA.SCORERS]
    os.makedirs(os.path.join(raw, "s2"), exist_ok=True)
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="")
    for set_name, scorer in todo:
        out = os.path.join(raw, set_name, f"{scorer}.jsonl")
        if os.path.exists(out):
            raise SystemExit(f"refusing to overwrite {out}")
        expected = RA.nlines(inputs[set_name])
        for attempt in (1, 2):
            p = subprocess.run([sys.executable, os.path.join(HERE, "run_experiment_v1_1.py"), scorer, set_name,
                                inputs[set_name], out], capture_output=True, text=True, env=env, timeout=21600)
            ok = p.returncode == 0 and os.path.exists(out) and RA.nlines(out) == expected
            if ok:
                break
            log["retries"].append({"set": set_name, "scorer": scorer, "attempt": attempt, "rc": p.returncode,
                                   "stderr_tail": p.stderr[-1500:]})
            if os.path.exists(out):
                os.remove(out)
        if not ok:
            raise SystemExit(f"infrastructure failure after retry: {set_name}/{scorer}")
        os.chmod(out, 0o444)
        log["runs"].append({"set": set_name, "scorer": scorer, "n": expected, "sha256": RA.sha(out),
                            "stdout": p.stdout.strip()[-400:]})
    log["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lp = os.path.join(raw, "run_log.json")
    json.dump(log, open(lp, "w"), indent=1)
    os.chmod(lp, 0o444)
    print(json.dumps({"runs": len(log["runs"]), "retries": len(log["retries"])}))


if __name__ == "__main__":
    main()
