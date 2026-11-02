#!/usr/bin/env python3
"""Run ONE MAIN_AUDIT adapter on a fixture in an isolated process (audit-run-adapter-v1).

  python run_adapter.py <scorer> <fixture.json> [--repeats N]

- Network is blocked BEFORE the scorer is imported: socket connect / getaddrinfo raise. Any network attempt therefore
  surfaces as an exception (and the scorer is then not network-free).
- CUDA is hidden (CUDA_VISIBLE_DEVICES="").
- Refuses any fixture that is not the the adapter-readiness check smoke fixture (S1/S2/S3 must not be run in the adapter-readiness check).
- Prints one JSON object: import status, per-case native outputs/verdicts for every repeat, timings, peak RSS.
"""
import json
import os
import resource
import socket
import sys
import time
import traceback

os.environ["CUDA_VISIBLE_DEVICES"] = ""
sys.dont_write_bytecode = True  # keep pinned vendor checkouts pristine (no __pycache__ inside external/)


class NetworkBlocked(RuntimeError):
    pass


def _blocked(*a, **k):
    raise NetworkBlocked("network access attempted during MAIN_AUDIT scoring")


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked

ALLOWED_FIXTURE_IDS = {"audit-smoke-v1"}


def main():
    scorer, fixture_path = sys.argv[1], sys.argv[2]
    repeats = int(sys.argv[sys.argv.index("--repeats") + 1]) if "--repeats" in sys.argv else 5
    fixture = json.load(open(fixture_path))
    if fixture.get("fixture_id") not in ALLOWED_FIXTURE_IDS:
        raise SystemExit(f"refused: fixture {fixture.get('fixture_id')!r} is not a the adapter-readiness check smoke fixture")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import audit_adapters as A

    rec = {"scorer": scorer, "python": sys.version.split()[0], "import_ok": False, "cases": []}
    t0 = time.perf_counter()
    try:
        score = A.LOADERS[scorer]()
        rec["import_ok"] = True
    except Exception as e:
        rec["import_error"] = f"{type(e).__name__}: {e}"
        rec["traceback"] = traceback.format_exc()[-2000:]
    rec["import_seconds"] = round(time.perf_counter() - t0, 4)
    calls, t_calls = 0, 0.0
    if rec["import_ok"]:
        for case in fixture["cases"]:
            runs = []
            for _ in range(repeats):
                t = time.perf_counter()
                try:
                    native, verdict = score(case)
                    runs.append({"native": native, "verdict": verdict})
                except Exception as e:
                    runs.append({"error": f"{type(e).__name__}: {e}"})
                t_calls += time.perf_counter() - t
                calls += 1
            rec["cases"].append({"case_id": case["case_id"], "runs": runs})
    rec["seconds_per_call"] = round(t_calls / calls, 6) if calls else None
    rec["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)
    rec["loaded_modules"] = len(sys.modules)
    rec["torch_or_cuda_loaded"] = any(m.split(".")[0] in {"torch", "tensorflow", "jax", "cupy"} for m in sys.modules)
    print(json.dumps(rec))


if __name__ == "__main__":
    main()
