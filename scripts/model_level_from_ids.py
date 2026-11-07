#!/usr/bin/env python3
"""Rebuild the POST-HOC model-level table (2 models x 138 questions = 276 units) from released IDs only.

  python3 scripts/model_level_from_ids.py <dataset_repo>/model_outputs/s2_not_scored_units.json

The frozen script studies/validation_repair/validity_repair/code/model_level.py reads the raw pilot predictions, which are
withheld, only to list the 138 G0 question IDs. Every G0 unit is either scored (case ID `S2-<model>|<question>` in the
released s2_results.csv) or not scored (unit ID `<model>|<question>` in the dataset repository's
s2_not_scored_units.json), so the same 138 IDs are the union of the two. This script runs the frozen script's source
unchanged except for three documented substitutions (question-ID source, unscored-unit path, output directory), writes
to rebuild/model_level/, and compares the result with the frozen model_level_sensitivity/ files byte for byte.
The analysis stays descriptive and post hoc; nothing here changes its interpretation."""
import hashlib, json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FROZEN_DIR = "studies/validation_repair/validity_repair"
SRC = FROZEN_DIR + "/code/model_level.py"
G0_BLOCK = '''g0 = {}
for m in MODELS:
    rs = [json.loads(l) for l in open(os.path.join(ROOT, f"withheld/pilot_predictions/predictions/extracted_{m}.jsonl"))]
    g0[m] = sorted({r["canonical_id"] for r in rs if r["graph_variant"] == "G0"})
'''
G0_FROM_IDS = '''g0 = {}
for m in MODELS:  # artifact substitution: question IDs from released scored + unscored unit IDs (see model_level_from_ids.py)
    ids = {r["case_id"].split("|", 1)[1] for r in csv.DictReader(open(os.path.join(MAIN_AUDIT, "s2_results.csv"))) if r["case_id"].startswith(f"S2-{m}|")}
    ids |= {u["unit_id"].split("|", 1)[1] for u in json.load(open(NOT_SCORED_FILE)) if u["unit_id"].startswith(f"{m}|")}
    g0[m] = sorted(ids)
'''
NOT_SCORED_OLD = 'os.path.join(MAIN_AUDIT, "pairs/s2_not_scored_units.json")'
OUT_OLD = 'OUT = os.path.join(ROOT, "studies/validation_repair/validity_repair/model_level_sensitivity")'


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def rebuild(root, not_scored_file, out_dir):
    src = open(os.path.join(root, SRC), encoding="utf-8").read()
    for old in (G0_BLOCK, NOT_SCORED_OLD, OUT_OLD):
        if src.count(old) != 1:
            raise SystemExit(f"frozen model_level.py does not contain the expected block exactly once: {old[:60]!r}")
    src = src.replace(G0_BLOCK, G0_FROM_IDS).replace(NOT_SCORED_OLD, "NOT_SCORED_FILE").replace(OUT_OLD, "OUT = OUT_DIR")
    ns = {"__name__": "model_level_rebuild", "__file__": os.path.join(root, SRC), "NOT_SCORED_FILE": not_scored_file, "OUT_DIR": out_dir}
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(src, SRC + " (artifact substitution)", "exec"), ns)  # ROOT inside resolves from __file__
    frozen = os.path.join(root, FROZEN_DIR, "model_level_sensitivity")
    same_csv = sha(os.path.join(out_dir, "model_level_ex.csv")) == sha(os.path.join(frozen, "model_level_ex.csv"))
    same_json = json.load(open(os.path.join(out_dir, "summary.json"))) == json.load(open(os.path.join(frozen, "summary.json")))
    return {"table": ns["res"]["primary"], "summary": ns["res"], "byte_identical": {"model_level_ex.csv": same_csv, "summary.json": same_json}}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: model_level_from_ids.py <dataset_repo>/model_outputs/s2_not_scored_units.json")
    r = rebuild(ROOT, os.path.abspath(sys.argv[1]), os.path.join(ROOT, "rebuild", "model_level"))
    print(json.dumps({"population": r["summary"]["population"], "identical_to_frozen": r["byte_identical"]}, indent=1))
    sys.exit(0 if all(r["byte_identical"].values()) else 1)
