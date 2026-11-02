#!/usr/bin/env python3
"""Run ONE frozen MAIN_AUDIT adapter over ONE experimental set, once per case (audit-run-experiment-v1.1).

v1.1 (infrastructure-only change, 2026-10-30, after the secondary neo4j-labs Jaccard scorer stalled on a 67,131-row
S3 pair due to its O(rows^2) greedy alignment): adds a per-case wall-clock timeout CASE_TIMEOUT_S = 120 via SIGALRM.
A case exceeding it is recorded as verdict "ERROR:CaseTimeout" (a native-runtime outcome; never retried). Scoring
logic, adapters and conversion are unchanged from v1.

  python run_experiment.py <scorer> <set: s1|s2|s3> <input.jsonl> <output.jsonl>

- Imports the FROZEN Study-13 adapters only after verifying audit_adapters.py SHA-256 against the readiness freeze.
- Same isolation as the readiness runner: network blocked before import, CUDA hidden, no bytecode writes.
- S1 records (Study-12 format) are converted to the MAIN_AUDIT representation by representation-only mapping
  (columns = ref/pred_columns; rows = [row_dict[c] for c in columns]).
- Each case is scored exactly once. A per-case exception is a result: verdict "ERROR:<ExceptionClass>".
"""
import hashlib
import json
import os
import socket
import sys
import signal
import time

os.environ["CUDA_VISIBLE_DEVICES"] = ""
sys.dont_write_bytecode = True


class NetworkBlocked(RuntimeError):
    pass


def _blocked(*a, **k):
    raise NetworkBlocked("network access attempted during MAIN_AUDIT scoring")


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked

CASE_TIMEOUT_S = 120


class CaseTimeout(Exception):
    pass


def _alarm(signum, frame):
    raise CaseTimeout(f"case exceeded {CASE_TIMEOUT_S} s")


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
ADAPTER_DIR = os.path.join(ROOT, "studies", "adapter_readiness", "audit_readiness", "code")
READINESS = os.path.join(ROOT, "studies", "adapter_readiness", "audit_readiness", "frozen", "20261029T181645Z_audit_readiness")


def s1_to_pair(c):
    def side(q, cols, rows):
        return {"query": q, "columns": list(cols), "rows": [[r[k] for k in cols] for r in rows]}
    return {"case_id": c["case_id"],
            "reference": side(c["ref_query"], c["ref_columns"], c["reference_result"]),
            "prediction": side(c["pred_query"], c["pred_columns"], c["predicted_result"])}


def main():
    scorer, set_name, inp, outp = sys.argv[1:5]
    frozen = json.load(open(os.path.join(READINESS, "adapter_manifest.json")))["code_sha256"]["audit_adapters.py"]
    actual = hashlib.sha256(open(os.path.join(ADAPTER_DIR, "audit_adapters.py"), "rb").read()).hexdigest()
    if actual != frozen:
        raise SystemExit(f"audit_adapters.py hash {actual} != frozen {frozen}")
    sys.path.insert(0, ADAPTER_DIR)
    import audit_adapters as A
    score = A.LOADERS[scorer]()
    t0 = time.perf_counter()
    n = 0
    with open(outp, "w", encoding="utf-8", newline="\n") as out:
        for line in open(inp, encoding="utf-8"):
            rec = json.loads(line)
            pair = s1_to_pair(rec) if set_name == "s1" else rec
            signal.signal(signal.SIGALRM, _alarm)
            signal.alarm(CASE_TIMEOUT_S)
            try:
                native, verdict = score(pair)
                row = {"case_id": pair["case_id"], "scorer": scorer, "native": native, "verdict": verdict}
            except Exception as e:
                row = {"case_id": pair["case_id"], "scorer": scorer, "native": None,
                       "verdict": f"ERROR:{type(e).__name__}", "error": str(e)[:300]}
            finally:
                signal.alarm(0)
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    print(json.dumps({"scorer": scorer, "set": set_name, "n": n, "seconds": round(time.perf_counter() - t0, 3),
                      "adapter_sha256": actual, "runner": "v1.1", "case_timeout_s": CASE_TIMEOUT_S}))


if __name__ == "__main__":
    main()
