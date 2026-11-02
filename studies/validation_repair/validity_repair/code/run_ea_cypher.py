#!/usr/bin/env python3
"""Run the Text2GQL repository's second released evaluator, contrib/standalone_text2graph_scripts/reference/ea_cypher.py,
on frozen result pairs (the validation repair, PLAN B2–B4). Local, CPU, no database, no network.

  python3.12 studies/validation_repair/validity_repair/code/run_ea_cypher.py

`ExecutionEvaluator.compare_results` is loaded verbatim (ast source segment) from the git blob at the pinned commit and is
not edited. Rows are given as dicts in column order (what `session.run(q).data()` returns), using the same conversion as
the frozen MAIN_AUDIT adapters (`dict(zip(columns, row))`). Writes text2gql/ea_cypher_verdicts.csv and ea_cypher_summary.json."""
import ast, csv, hashlib, json, os, subprocess, textwrap
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
OUT = os.path.join(ROOT, "studies/validation_repair/validity_repair/text2gql")
BLOB = "contrib/standalone_text2graph_scripts/reference/ea_cypher.py"
PIN = "ab296fab179e806cd3ad2e659e9f5dc61bd1af3e"
MAIN_AUDIT = "studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final"
COND = "artifact/staging/conditional/studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final/pairs"


def load_compare():
    src = subprocess.run(["git", "-C", os.path.join(ROOT, "external/tugraph_driver"), "show", f"{PIN}:{BLOB}"],
                         capture_output=True, text=True, check=True).stdout
    cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "ExecutionEvaluator")
    fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "compare_results")
    seg = textwrap.dedent(ast.get_source_segment(src, fn))
    ns = {}
    exec(compile(seg, f"{BLOB}::ExecutionEvaluator.compare_results", "exec"), ns)
    method = ns["compare_results"]  # an instance method that never reads `self`
    return (lambda gold, pred: method(None, gold, pred)), hashlib.sha256(src.encode()).hexdigest(), hashlib.sha256(seg.encode()).hexdigest()


def as_dicts(side):
    return [dict(zip(side["columns"], r)) for r in side["rows"]]


def s1_pair(c):
    side = lambda cols, rows: {"columns": list(cols), "rows": [[r[k] for k in cols] for r in rows]}
    return {"case_id": c["case_id"], "reference": side(c["ref_columns"], c["reference_result"]),
            "prediction": side(c["pred_columns"], c["predicted_result"])}


def jl(p): return [json.loads(l) for l in open(os.path.join(ROOT, p), encoding="utf-8")]
def csvd(p, key="case_id"): return {r[key]: r for r in csv.DictReader(open(os.path.join(ROOT, p), encoding="utf-8"))}


SETS = [  # (set, pairs, frozen verdict file (case_id -> row with 'tugraph'), class field)
    ("s1_original", [s1_pair(c) for c in jl("studies/controlled_suite/audit/s1/s1_cases.jsonl")], f"{MAIN_AUDIT}/s1_results.csv", "dimension"),
    ("s1_corrected", [s1_pair(c) for c in jl("studies/validation_repair/validity_repair/s1_corrected/s1_corrected_cases.jsonl")],
     "studies/validation_repair/validity_repair/s1_corrected/s1_corrected_results.csv", "dimension"),
    ("s18", jl("studies/native_cypherturn_validation/native_cypher/frozen/20261030T083217Z_native_cypher_input/cases.jsonl"),
     "studies/native_cypherturn_validation/native_cypher/frozen/20261030T083338Z_native_cypher_results/s18_verdicts.csv", "family"),
    ("s20", jl("studies/native_cypherturn_stress/native_equivalence_stress/frozen/20261030T143740Z_input/cases.jsonl"),
     "studies/native_cypherturn_stress/native_equivalence_stress/frozen/20261030T143804Z_results/s20_verdicts.csv", "class"),
    ("s23", jl("studies/native_mind_the_query/mind_the_query_replication/frozen/20261031T180759Z_input/cases.jsonl"),
     "studies/native_mind_the_query/mind_the_query_replication/frozen/20261031T181038Z_results/s23_verdicts.csv", "class"),
    ("s2", jl(f"{COND}/s2_pairs.jsonl"), f"{MAIN_AUDIT}/s2_results.csv", None),
    ("s3", jl(f"{COND}/s3_pairs.jsonl"), f"{MAIN_AUDIT}/s3_results.csv", None),
]


def main():
    compare, blob_sha, fn_sha = load_compare()
    sanity = [compare([{"a": 1}], [{"a": 1}]), compare([{"a": 1}], [{"a": 2}])]  # identical accepted, different rejected
    if sanity != [True, False]:
        raise SystemExit(f"harness sanity check failed: {sanity}")
    rows, summary = [], {"evaluator": f"{BLOB}@{PIN[:8]} ExecutionEvaluator.compare_results", "blob_sha256": blob_sha,
                         "function_source_sha256": fn_sha, "sets": {}}
    for name, pairs, vfile, cfield in SETS:
        fz = csvd(vfile)
        per = defaultdict(lambda: {"n": 0, "ea_accept": 0, "metrics_accept": 0, "disagree": 0})
        for p in pairs:
            try:
                v = "1" if compare(as_dicts(p["reference"]), as_dicts(p["prediction"])) else "0"
            except Exception as e:
                v = f"ERROR:{type(e).__name__}"
            old = fz[p["case_id"]]["tugraph"]
            cls = fz[p["case_id"]].get(cfield, "-") if cfield else "-"
            rows.append({"set": name, "case_id": p["case_id"], "class": cls, "metrics_py_verdict": old, "ea_cypher_verdict": v,
                         "agree": old == v})
            c = per[cls]; c["n"] += 1; c["ea_accept"] += v == "1"; c["metrics_accept"] += old == "1"; c["disagree"] += old != v
        summary["sets"][name] = {"n": len(pairs), "disagreements": sum(x["disagree"] for x in per.values()),
                                 "by_class": dict(sorted(per.items()))}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "ea_cypher_verdicts.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    json.dump(summary, open(os.path.join(OUT, "ea_cypher_summary.json"), "w"), indent=1)
    for k, s in summary["sets"].items():
        print(k, "n", s["n"], "disagreements", s["disagreements"])
        for c, x in s["by_class"].items():
            if x["disagree"] or k in ("s20", "s23", "s18"): print("   ", c, x)


if __name__ == "__main__":
    main()
