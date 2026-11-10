"""S55H: replay the FROZEN Gate40 result pairs through the pinned released scorers. No live DB, no new inference.

Uses the unchanged frozen run_released_scorer() (hash/commit checks, JSON-domain gate, replay connector, network
blocked inside the runner). CypherLens is a primary audited adapter that the frozen wrapper does not list; it is run
with the SAME runner + the SAME pin checks in a clearly labelled Track-B-only path (flagged in the manifest).
"""
import csv, hashlib, json, os, subprocess, sys
from pathlib import Path

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"; sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score_predictions as sp

run_dir, art_root, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=False)
traces = [json.loads(l) for l in (run_dir / "execution_traces.jsonl").read_text().splitlines()]
project = [r for r in csv.DictReader((run_dir / "scorer_verdicts.csv").open())]
SCORERS = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cyspider", "neo4jlabs", "pc_v1_1"]
outputs, notes = {}, {}
for s in SCORERS:
    try:
        outputs[s] = sp.run_released_scorer(s, traces, out / ("raw_" + s), art_root)
        notes[s] = "frozen run_released_scorer"
    except Exception as e:
        notes[s] = "NOT EXECUTED: %s: %s" % (type(e).__name__, str(e)[:300])
# CypherLens (not in frozen wrapper allow-list): same runner, same pin checks, own work dir
try:
    pins = json.loads((art_root / "external/EXTERNAL_PINS.json").read_text())["repos"]
    pin = next(x for x in pins if x["local_dir"] == "cypherlens")
    tgt = art_root / "external/cypherlens"
    rev = subprocess.run(["git", "-C", str(tgt), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if rev != pin["commit"]:
        raise ValueError("commit drift")
    work = out / "raw_cypherlens"; work.mkdir()
    pairs = [{"case_id": t["model"] + "|" + t["question_id"], "reference": {"query": t["reference_query"], **t["reference"]},
              "prediction": {"query": t["predicted_query"], **t["prediction"]}} for t in traces if t["status"] == "scored"]
    (work / "pairs.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False, allow_nan=False) + "\n" for p in pairs))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    runner = art_root / "studies/corpus_audit/audit_analysis/code/run_experiment_v1_1.py"
    pr = subprocess.run([sys.executable, str(runner), "cypherlens", "s3", str(work / "pairs.jsonl"), str(work / "verdicts.jsonl")],
                        capture_output=True, text=True, timeout=1200, env=env)
    (work / "runner_stdout.log").write_text(pr.stdout); (work / "runner_stderr.log").write_text(pr.stderr)
    if pr.returncode: raise RuntimeError("runner failed; logs preserved")
    outputs["cypherlens"] = sp.jsonl(work / "verdicts.jsonl")
    notes["cypherlens"] = "Track-B-only path (not in frozen wrapper allow-list); same runner and pins"
except Exception as e:
    notes["cypherlens"] = "NOT EXECUTED: %s: %s" % (type(e).__name__, str(e)[:300])
rows = sp.analysis_rows(traces, project, outputs)
with (out / "scorer_verdicts_all.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["benchmark", "question_id", "model", "scorer", "verdict", "status", "origin"])
    w.writeheader(); w.writerows(rows)
raw = {s: {r["case_id"]: r for r in o} for s, o in outputs.items()}
(out / "raw_native_outputs.json").write_text(json.dumps(raw, indent=1, ensure_ascii=False))
pins_used = {s: sp.sha(art_root / "studies/adapter_readiness/audit_readiness/code/audit_adapters.py") for s in ["adapter"]}
(out / "scorer_execution_manifest.json").write_text(json.dumps({
    "input_traces_sha256": sp.sha(run_dir / "execution_traces.jsonl"), "artifact_copy": str(art_root),
    "adapter_sha256": pins_used["adapter"], "executed": sorted(outputs), "notes": notes,
    "units_per_scorer": {s: len(o) for s, o in outputs.items()}, "python": sys.version.split()[0]}, indent=1))
print(json.dumps(notes, indent=1)); print({s: len(o) for s, o in outputs.items()})
