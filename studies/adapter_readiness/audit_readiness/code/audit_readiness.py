#!/usr/bin/env python3
"""MAIN_AUDIT scorer readiness verification + freeze (audit-readiness-v1).

  python audit_readiness.py verify            # pins + smoke runs, prints the report, writes nothing
  python audit_readiness.py freeze            # same, then writes frozen/<UTC>_audit_readiness/

Runs ONLY the the adapter-readiness check smoke fixture. Never touches S1 / S2 / S3.
Gate (protocol audit-protocol-v1 §P9, the adapter-readiness check §14; threshold fixed in advance, never lowered):
  PASS iff >= 4 PRIMARY external scorers are RUNNABLE_UNCHANGED or RUNNABLE_WITH_THIN_ADAPTER.
"""
import csv
import datetime
import hashlib
import io
import json
import os
import platform
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_adapters as A  # noqa: E402

ROOT = A.ROOT
S13 = os.path.join(ROOT, "studies", "adapter_readiness")
SMOKE = os.path.join(S13, "audit_import_smoke", "smoke_fixture.json")
EXPECTED = os.path.join(S13, "audit_import_smoke", "expected_native_verdicts.json")
PINS = os.path.join(ROOT, "external", "EXTERNAL_PINS.json")
OUTDIR = os.path.join(S13, "audit_readiness", "frozen")
GATE_THRESHOLD = 4
RUNNABLE = {"RUNNABLE_UNCHANGED", "RUNNABLE_WITH_THIN_ADAPTER"}

# Adapter classification is a property of the adapter design (audit_adapters.py), fixed before running:
ADAPTER_KIND = {
    "cypherturn": "RUNNABLE_WITH_THIN_ADAPTER",   # replay connector (connector is a parameter)
    "cypherbench": "RUNNABLE_WITH_THIN_ADAPTER",  # replay connector; seed 42 per protocol P3
    "gqlbench": "RUNNABLE_WITH_THIN_ADAPTER",     # nebula stub; fake neo4j driver emulating Result.to_df; pacing sleep off
    "tugraph": "RUNNABLE_WITH_THIN_ADAPTER",      # replay DB driver; `evaluate` stub (BLEU only)
    "pipecypher": "RUNNABLE_UNCHANGED",           # pure function answer_set_scores
    "cypherlens": "RUNNABLE_WITH_THIN_ADAPTER",   # EvaluationRow construction; main.py comparator wiring
    "cyspider": "RUNNABLE_WITH_THIN_ADAPTER",     # verbatim AST extraction (module connects at import); graph replay
    "neo4jlabs": "RUNNABLE_WITH_THIN_ADAPTER",    # verbatim notebook-cell extraction
    "pc_v1_1": "RUNNABLE_UNCHANGED",
}
STATIC_SAFETY = {
    "cypherturn": "SAFE_TO_IMPORT", "cypherbench": "SAFE_TO_IMPORT", "gqlbench": "SAFE_TO_IMPORT",
    "tugraph": "SAFE_TO_IMPORT", "pipecypher": "SAFE_TO_IMPORT", "cypherlens": "SAFE_TO_IMPORT",
    "cyspider": "REQUIRES_ISOLATION", "neo4jlabs": "REQUIRES_ISOLATION", "pc_v1_1": "SAFE_TO_IMPORT",
}


# Smoke deviations from the pre-run code-reading expectations that were investigated and shown to be the scorer's own
# behaviour (inputs verified intact at the scorer boundary), not adapter errors. The expectations file is NOT edited.
REVIEWED_DEVIATIONS = {
    ("cypherlens", "SMOKE-06"): (
        "CypherLens build_table canonicalises RETURN expressions by stripping the variable prefix, so gold "
        "'c.name AS city' and 'k.name AS country' both canonicalise to 'name'; its alignment pairs gold city with "
        "generated country and marks x.name generated-only (__MISSING__) -> exact_match 0. Verified by dumping "
        "comparison_table: adapter-supplied aliases and rows reach the scorer unchanged. Scorer behaviour, kept."),
}


def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def git(d, *a):
    return subprocess.check_output(["git", "-C", d] + list(a), text=True).strip()


def verify_pins():
    pins = json.load(open(PINS))
    out = {}
    for r in pins["repos"]:
        d = os.path.join(ROOT, "external", r["local_dir"])
        f = r["scorer_file"].split(" ")[0]
        rec = {"url": r["url"], "pinned_commit": r["commit"], "license": r["license"]}
        try:
            rec["local_commit"] = git(d, "rev-parse", "HEAD")
            rec["origin"] = git(d, "remote", "get-url", "origin")
            rec["dirty"] = bool(git(d, "status", "--porcelain"))
            rec["submodules"] = git(d, "submodule", "status")
            rec["scorer_sha256"] = sha256_file(os.path.join(d, f))
            rec["ok"] = (rec["local_commit"] == r["commit"] and not rec["dirty"] and not rec["submodules"]
                         and rec["scorer_sha256"] == r["scorer_sha256"]
                         and rec["origin"].removesuffix(".git") == r["url"])
        except Exception as e:  # missing checkout etc.
            rec["ok"], rec["error"] = False, f"{type(e).__name__}: {e}"
        out[r["local_dir"]] = rec
    return out


def run_scorer(name, hashseed):
    env = dict(os.environ, PYTHONHASHSEED=str(hashseed), CUDA_VISIBLE_DEVICES="", PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, os.path.join(HERE, "run_adapter.py"), name, SMOKE, "--repeats", "5"],
                       capture_output=True, text=True, env=env, timeout=600)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return {"scorer": name, "import_ok": False, "import_error": "runner failed", "stderr": p.stderr[-2000:]}


def classify(name, pin_ok, runs, expected):
    """-> (class, determinism, notes). runs = [record_hashseed0, record_hashseed1]."""
    notes = []
    if A.PIN_DIR[name] is not None and not pin_ok:
        return "NOT_RUNNABLE", "n/a", ["pin verification failed: not executed"]
    r0 = runs[0]
    if not r0.get("import_ok"):
        return "MISSING_RUNTIME_COMPONENT", "n/a", [r0.get("import_error", "import failed")]
    if r0.get("torch_or_cuda_loaded"):
        return "GPU_DEPENDENCY", "n/a", ["GPU framework imported"]
    errs = [c["case_id"] + ": " + run["error"] for c in r0["cases"] for run in c["runs"] if "error" in run]
    if any("NetworkBlocked" in e for e in errs):
        return "NOT_RUNNABLE", "n/a", ["network required at scoring time"] + errs[:3]
    if errs:
        return "NOT_RUNNABLE", "n/a", errs[:3]
    # determinism: 5 repeats within each process, and across two processes with different PYTHONHASHSEED
    sig = [[(c["case_id"], tuple((x["native"], x["verdict"]) for x in c["runs"])) for c in r["cases"]] for r in runs]
    within = all(len(set(t)) == 1 for r in sig for _, t in r)
    across = sig[0] == sig[1]
    det = "DETERMINISTIC" if within and across else "NONDETERMINISTIC"
    if det != "DETERMINISTIC":
        notes.append("output differs across repeats or hash seeds")
    mism = []
    for c in r0["cases"]:
        exp = expected["expected"][c["case_id"]].get(name)
        got = c["runs"][0]["verdict"]
        if exp is not None and exp != got:
            if (name, c["case_id"]) in REVIEWED_DEVIATIONS:
                notes.append(f"REVIEWED deviation {c['case_id']} (expected {exp}, got {got}): "
                             + REVIEWED_DEVIATIONS[(name, c["case_id"])])
            else:
                mism.append(f"{c['case_id']}: expected {exp}, got {got}")
    if mism:
        notes.append("smoke verdict differs from code-reading expectation (investigate adapter): " + "; ".join(mism))
    cls = ADAPTER_KIND[name] if det == "DETERMINISTIC" and not mism else "SEMANTICS_NOT_ISOLATABLE_PENDING_REVIEW"
    return cls, det, notes


def import_gate(classes, primary=A.PRIMARY, threshold=GATE_THRESHOLD):
    n = sum(1 for s in primary if classes.get(s) in RUNNABLE)
    return ("PASS" if n >= threshold else "FAIL"), n


def build():
    pins = verify_pins()
    expected = json.load(open(EXPECTED))
    rows, raw = [], {}
    for name in A.PRIMARY + A.SECONDARY:
        pin_dir = A.PIN_DIR[name]
        pin_ok = pins[pin_dir]["ok"] if pin_dir else True
        runs = [run_scorer(name, 0), run_scorer(name, 1)] if pin_ok else [{"import_ok": False}, {"import_ok": False}]
        raw[name] = runs
        cls, det, notes = classify(name, pin_ok, runs, expected)
        r0 = runs[0]
        rows.append({
            "scorer": name, "role": "PRIMARY" if name in A.PRIMARY else "SECONDARY",
            "repo_dir": pin_dir or "project", "commit": pins[pin_dir]["local_commit"] if pin_dir else "project",
            "pin_ok": pin_ok, "static_safety": STATIC_SAFETY[name], "classification": cls, "determinism": det,
            "import_seconds": r0.get("import_seconds"), "seconds_per_call": r0.get("seconds_per_call"),
            "est_seconds_per_100_pairs": round(100 * r0["seconds_per_call"], 3) if r0.get("seconds_per_call") else None,
            "peak_rss_mb": r0.get("peak_rss_mb"), "gpu": "NO", "network_at_runtime": "NO (blocked; none attempted)"
            if cls in RUNNABLE else "n/a", "api_key": "NO", "cost_usd": 0, "notes": " | ".join(notes),
        })
    gate, n = import_gate({r["scorer"]: r["classification"] for r in rows})
    return pins, rows, raw, gate, n


def env_manifest():
    pkgs = {}
    for m in ["neo4j", "pandas", "numpy", "pydantic", "yaml", "tqdm", "requests"]:
        try:
            mod = __import__(m)
            pkgs[m] = getattr(mod, "__version__", "?")
        except Exception as e:
            pkgs[m] = f"MISSING ({type(e).__name__})"
    return {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
            "machine": platform.machine(), "packages": pkgs, "packages_installed_this_session": [],
            "gpu": "none used (CUDA_VISIBLE_DEVICES='')", "network_at_scoring": "blocked in-process"}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "verify"
    pins, rows, raw, gate, n = build()
    summary = {"gate": gate, "runnable_primary": n, "threshold": GATE_THRESHOLD,
               "classes": {r["scorer"]: r["classification"] for r in rows}}
    print(json.dumps({"pins_ok": {k: v["ok"] for k, v in pins.items()}, "rows": rows, **summary}, indent=1))
    if mode != "freeze":
        return
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = os.path.join(OUTDIR, f"{stamp}_audit_readiness")
    os.makedirs(out)
    with open(os.path.join(out, "scorer_readiness.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    with open(os.path.join(out, "smoke_results.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scorer", "case_id", "hashseed", "repeat", "native_output", "verdict", "error"])
        for name, runs in raw.items():
            for hs, rec in enumerate(runs):
                for c in rec.get("cases", []):
                    for i, x in enumerate(c["runs"]):
                        w.writerow([name, c["case_id"], hs, i, x.get("native"), x.get("verdict"), x.get("error")])
    code_files = ["audit_adapters.py", "run_adapter.py", "audit_readiness.py"]
    adapter_manifest = {
        "adapters_version": "audit-adapters-v1", "protocol": "audit-protocol-v1 (tag audit-protocol-v1)",
        "code_sha256": {f: sha256_file(os.path.join(HERE, f)) for f in code_files},
        "cyspider_extracted_function_sha256": hashlib.sha256(
            A.extract_function_source(A.CYSPIDER_FILE, "eval_exec_match").encode()).hexdigest(),
        "neo4jlabs_cell5_sha256": hashlib.sha256(A.neo4jlabs_cell_source().encode()).hexdigest(),
        "invocation": {"cypherbench_gqlbench_seed": A.SEED, "repeats": 5, "hashseeds": [0, 1],
                       "network": "blocked", "cuda": "hidden"},
        "primary": A.PRIMARY, "secondary": A.SECONDARY, "exclusions": [r["scorer"] for r in rows
                                                                      if r["classification"] not in RUNNABLE],
    }
    json.dump(adapter_manifest, open(os.path.join(out, "adapter_manifest.json"), "w"), indent=2)
    json.dump(env_manifest(), open(os.path.join(out, "environment_manifest.json"), "w"), indent=2)
    json.dump(json.load(open(SMOKE)), open(os.path.join(out, "smoke_fixture.json"), "w"), indent=2)
    json.dump({"pins": pins, "summary": summary, "s1_used": False, "s2_used": False, "s3_used": False,
               "smoke_fixture_sha256": sha256_file(SMOKE), "expected_sha256": sha256_file(EXPECTED),
               "s1_cases_sha256_untouched": sha256_file(os.path.join(ROOT, "studies", "controlled_suite", "audit", "s1",
                                                                     "s1_cases.jsonl")),
               "created_utc": stamp}, open(os.path.join(out, "integrity_report.json"), "w"), indent=2)
    with open(os.path.join(out, "README_FINALIZATION.txt"), "w") as f:
        f.write(f"MAIN_AUDIT readiness freeze {stamp}\nGate: {gate} ({n}/{len(A.PRIMARY)} primary runnable; threshold "
                f"{GATE_THRESHOLD}).\nSmoke fixture only; S1/S2/S3 NOT run. Adapters frozen by hash in "
                f"adapter_manifest.json. Do not edit; any change requires a new versioned freeze.\n")
    lines = []
    for fn in sorted(os.listdir(out)):
        if fn != "hashes.sha256":
            lines.append(f"{sha256_file(os.path.join(out, fn))}  {fn}")
    open(os.path.join(out, "hashes.sha256"), "w").write("\n".join(lines) + "\n")
    print("FROZEN:", out)


if __name__ == "__main__":
    main()
