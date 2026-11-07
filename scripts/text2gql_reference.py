#!/usr/bin/env python3
"""Re-run the Text2GQL repository's SECOND released evaluator (reference/ea_cypher.py, ExecutionEvaluator.compare_results)
on frozen result pairs and compare every verdict with the frozen file
studies/validation_repair/validity_repair/text2gql/ea_cypher_verdicts.csv. Local, CPU, no database.

  python3 scripts/text2gql_reference.py [--dataset DIR] [--native-rebuild] [SET ...]
  SET: s1_corrected s1_original (released here); s3 s2 (dataset repository: corpus/s3_pairs.jsonl,
       model_outputs/s2_pairs.jsonl); s18 s20 s23 (native cases: frozen copy if present, else rebuild/<set>/ from
       scripts/full_native.sh). Default: every set whose input is available; unavailable sets are BOUNDARY.

The pipeline evaluator (impl/evaluation/metrics.py, "Text2GQL driver") is one of the seven primary scorers and is
re-scored by full_rescore.py; this script covers only the reference script. Its comparison function and the helper
functions (load_compare, as_dicts, s1_pair) are taken verbatim from the frozen run_ea_cypher.py via its syntax tree;
only input locations are parameterised. Needs external/tugraph_driver (third_party/fetch_scorers.sh) because the
function is loaded from the git blob at the pinned commit. Writes only rebuild/text2gql/.

Native sets: Mind the Query (s23) rebuilds byte-identically, so the per-case comparison is exact. CypherTurn rebuilds
(s18, s20) may admit a slightly different case set (Neo4j load order; see compare_verdicts.py), so for them the check
is per-case on common cases plus per-class disagreement counts, and any difference in case set is reported."""
import argparse, ast, csv, glob, hashlib, json, os, sys
from collections import Counter
sys.dont_write_bytecode = True

ROOT = os.path.abspath(os.environ.get("ARTIFACT_ROOT") or os.path.join(os.path.dirname(__file__), ".."))
V = "studies/validation_repair/validity_repair"
FROZEN_SRC = V + "/code/run_ea_cypher.py"
FROZEN_OUT = V + "/text2gql/ea_cypher_verdicts.csv"
MAIN_AUDIT = "studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final"
NATIVE = {  # set -> (frozen input dir, frozen verdicts, class field)
    "s18": ("studies/native_cypherturn_validation/native_cypher/frozen/20261030T083217Z_native_cypher_input",
            "studies/native_cypherturn_validation/native_cypher/frozen/20261030T083338Z_native_cypher_results/s18_verdicts.csv", "family"),
    "s20": ("studies/native_cypherturn_stress/native_equivalence_stress/frozen/20261030T143740Z_input",
            "studies/native_cypherturn_stress/native_equivalence_stress/frozen/20261030T143804Z_results/s20_verdicts.csv", "class"),
    "s23": ("studies/native_mind_the_query/mind_the_query_replication/frozen/20261031T180759Z_input",
            "studies/native_mind_the_query/mind_the_query_replication/frozen/20261031T181038Z_results/s23_verdicts.csv", "class"),
}


def frozen_functions():
    """Execute only the function definitions of the frozen script (never its import-time SETS list or main())."""
    src = open(os.path.join(ROOT, FROZEN_SRC), encoding="utf-8").read()
    tree = ast.parse(src)
    keep = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef))
            or (isinstance(n, ast.Assign) and all(isinstance(t, ast.Name) and t.id in {"BLOB", "PIN"} for t in n.targets))]
    ns = {"ROOT": ROOT, "__name__": "frozen_run_ea_cypher"}
    exec(compile(ast.Module(body=keep, type_ignores=[]), FROZEN_SRC + " (function definitions only)", "exec"), ns)
    return ns


def jl(path): return [json.loads(l) for l in open(path, encoding="utf-8")]


def native_input(name):
    d, _, _ = NATIVE[name]
    f = os.path.join(ROOT, d, "cases.jsonl")
    if os.path.exists(f):
        return f, "frozen"
    cand = sorted(glob.glob(os.path.join(ROOT, "rebuild", name, "frozen", "*_input", "cases.jsonl")))
    return (cand[-1], "rebuilt") if cand else (None, None)


def sources(args, fn):
    out = {}
    s1 = lambda p: [fn["s1_pair"](c) for c in jl(os.path.join(ROOT, p))]
    out["s1_corrected"] = (lambda: s1(V + "/s1_corrected/s1_corrected_cases.jsonl"), "released", None)
    out["s1_original"] = (lambda: s1("studies/controlled_suite/audit/s1/s1_cases.jsonl"), "released", None)
    for name, rel in (("s3", "corpus/s3_pairs.jsonl"), ("s2", "model_outputs/s2_pairs.jsonl")):
        f = os.path.join(args.dataset, rel) if args.dataset else None
        out[name] = ((lambda f=f: jl(f)), "dataset", None) if f and os.path.exists(f) else (None, "needs --dataset (dataset repository)", None)
    for name in NATIVE:
        f, how = native_input(name)
        out[name] = ((lambda f=f: jl(f)), how, f) if f else (None, f"needs native rebuild: scripts/full_native.sh {name}", None)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=os.environ.get("DATASET_DIR") or os.environ.get("CORPUS_PAIRS_DIR"))
    ap.add_argument("--require", action="store_true", help="fail if a requested set is unavailable")
    ap.add_argument("sets", nargs="*")
    args = ap.parse_args()
    fn = frozen_functions()
    compare, blob_sha, fn_sha = fn["load_compare"]()
    if [compare([{"a": 1}], [{"a": 1}]), compare([{"a": 1}], [{"a": 2}])] != [True, False]:
        sys.exit("harness sanity check failed")
    frozen = {}
    for r in csv.DictReader(open(os.path.join(ROOT, FROZEN_OUT), encoding="utf-8")):
        frozen[(r["set"], r["case_id"])] = r
    src = sources(args, fn)
    wanted = args.sets or list(src)
    out_dir = os.path.join(ROOT, "rebuild", "text2gql"); os.makedirs(out_dir, exist_ok=True)
    rows, bad, missing = [], 0, []
    print(f"evaluator blob sha256 {blob_sha[:16]}… function sha256 {fn_sha[:16]}…")
    for name in wanted:
        load, how, path = src[name]
        if load is None:
            missing.append(name); print(f"[BOUNDARY] {name}: {how}"); continue
        pairs = load()
        got = {}
        for p in pairs:
            try:
                got[p["case_id"]] = "1" if compare(fn["as_dicts"](p["reference"]), fn["as_dicts"](p["prediction"])) else "0"
            except Exception as e:  # recorded exactly as the frozen script records it
                got[p["case_id"]] = f"ERROR:{type(e).__name__}"
        fz = {cid: r for (st, cid), r in frozen.items() if st == name}
        common = set(got) & set(fz)
        diff = sorted(c for c in common if got[c] != fz[c]["ea_cypher_verdict"])
        only_new, only_frozen = sorted(set(got) - set(fz)), sorted(set(fz) - set(got))
        dis_frozen = Counter(r["class"] for r in fz.values() if r["agree"] == "False")
        dis_common = Counter(fz[c]["class"] for c in common if got[c] != fz[c]["metrics_py_verdict"])
        exact = not diff and not only_new and not only_frozen
        verdict_level = not diff and (exact or (how == "rebuilt" and name in ("s18", "s20")))
        bad += not verdict_level
        for c in sorted(got):
            rows.append({"set": name, "case_id": c, "ea_cypher_verdict": got[c], "frozen_ea_cypher_verdict": fz.get(c, {}).get("ea_cypher_verdict", "")})
        print(f"[{'OK' if verdict_level else 'FAIL'}] {name} ({how}): {len(got)} cases, {len(diff)} verdict differences vs frozen, "
              f"{len(only_new)} new / {len(only_frozen)} missing cases; frozen driver-vs-reference disagreements {sum(dis_frozen.values())} "
              f"{dict(sorted(dis_frozen.items()))}" + ("" if exact else f"; on common cases {sum(dis_common.values())} {dict(sorted(dis_common.items()))}"))
        if path and how == "rebuilt":
            fh = {l.split()[1]: l.split()[0] for l in open(os.path.join(ROOT, NATIVE[name][0], "hashes.sha256"))}.get("cases.jsonl")
            print(f"      rebuilt cases.jsonl {'matches' if hashlib.sha256(open(path, 'rb').read()).hexdigest() == fh else 'differs from'} the frozen hash")
    with open(os.path.join(out_dir, "ea_cypher_rebuilt.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["set", "case_id", "ea_cypher_verdict", "frozen_ea_cypher_verdict"]); w.writeheader(); w.writerows(rows)
    status = "FAIL" if bad else ("PASS" if not missing else "PARTIAL")
    print(f"TEXT2GQL REFERENCE EVALUATOR: {status} ({len(wanted) - len(missing)} sets re-scored, {bad} failing, {len(missing)} not available here)")
    sys.exit(1 if bad or (args.require and missing) else 0)


if __name__ == "__main__":
    main()
