#!/usr/bin/env python3
"""study S23 oracle validator + input freeze (s23-oracle-v1). Requires an ISOLATED throwaway Neo4j (run_s23_oracle.sh).

Two modes:
  eval-graph <candidates.jsonl> <graph> <bolt_uri> <user> <password> <work_dir> <dump_path>
      One Mind the Query graph is already loaded (neo4j-admin database load) into the throwaway container. Fingerprint
      the graph, run every candidate's reference and candidate query twice in READ transactions, fingerprint again
      (abort on any change) and apply the class rule `check()`. Writes <work_dir>/<graph>.json. NO scorer is run.
  freeze <candidates.jsonl> <work_dir> <prereg_dir> <out_base_dir>
      Merge the per-graph results, select (first passing variant per source; first QUOTA passing sources per class in
      generator order) and write the frozen input package. NO scorer is imported or run here.

Cell identity and canonicalisation are the FROZEN study S20 functions (s20_oracle.canon / cell), imported unchanged.
Pre-declared exclusions: SQL-looking text; reference text == candidate text; execution error; graph / temporal / other
non-JSON values; non-deterministic result across two runs; > MAX_ROWS rows; empty reference.
"""
import csv, datetime, hashlib, json, math, os, re, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "studies", "native_cypherturn_stress", "native_equivalence_stress", "code"))
from s20_oracle import canon, cell, is_int, looks_sql          # frozen S20 helpers (unchanged)
from s23_rules import QUOTA, EPSILON_REL, CLASSES, GRAPHS
from s23_parse import count_order_by, has_order_skip_limit_anywhere

MAX_ROWS = 5000
ORACLE_DEFS = {
    "R1_numeric_type": "same column names (same order) and row count; exactly one column differs; in it every reference "
                       "cell is an integer (not bool) and the aligned candidate cell is a float with float(ref) == cand; "
                       "all other columns identical (type-aware) row by row",
    "R2_float_tolerance": f"same column names and row count; exactly one column differs; in it every aligned pair is two "
                          f"non-NaN floats with |cand - ref| <= {EPSILON_REL} * max(1, |ref|); at least one pair has a "
                          f"non-zero difference; all other columns identical row by row",
    "R3_row_order": "same column names; identical rows including types as multisets; row sequences differ; reference "
                    "text has no ORDER BY / SKIP / LIMIT",
    "R4_duplicates": "same column names; reference has no duplicate rows; same set of distinct rows (types included); "
                     "candidate has at least one duplicate row; candidate de-duplicated in first-occurrence order equals "
                     "the reference sequence",
    "R5_column_order": ">= 2 columns; candidate column list is the reverse of the reference column list and differs from "
                       "it; same row count; every row identical cell by cell when aligned by column name (type-aware); "
                       "same row sequence",
    "R6_reference_order": "reference text has exactly one ORDER BY and no SKIP / LIMIT; candidate text has no ORDER BY; "
                          "same column names; identical rows including types as multisets; row sequences differ",
    "R7_list_order": "same column names and row count; exactly one column differs; in it every aligned pair is two lists "
                     "of scalars with the same elements as multisets (type-aware) and at least one row's list sequence "
                     "differs; all other columns identical row by row",
    "R8_null_natural": "results identical including column names, types, row order and NULL positions; at least one "
                       "NULL cell and at least one non-NULL cell (NULLs occur naturally; nothing is appended)",
    "C0_column_name_control": "study S18 T1 / study S20 D6 rule: same column count and value multiset; column names differ",
}


class NonJSON(Exception):
    pass


def rows_t(res, keys=None):
    keys = keys or res["keys"]
    return [tuple(cell(r[k]) for k in keys) for r in res["rows"]]


def diff_cols(ref, cand):
    return [k for k in ref["keys"] if any(cell(a[k]) != cell(b[k]) for a, b in zip(ref["rows"], cand["rows"]))]


def null_profile(res):
    """per column containing NULL: type class of its non-NULL values (numeric / text / bool / all_null / mixed)."""
    out = {}
    for k in res["keys"]:
        col = [r[k] for r in res["rows"]]
        if not any(v is None for v in col): continue
        nn = [v for v in col if v is not None]
        if not nn: t = "all_null"
        elif all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in nn): t = "numeric"
        elif all(isinstance(v, str) for v in nn): t = "text"
        elif all(isinstance(v, bool) for v in nn): t = "bool"
        else: t = "mixed"
        out[k] = {"type": t, "nulls": len(col) - len(nn), "non_nulls": len(nn)}
    return out


def check(cls, ref, cand, ref_q="", cand_q=""):
    """Pure class rule. ref/cand = {"keys": [...], "rows": [{k: v}]}. -> (admit, detail dict or reason str)."""
    if not ref["rows"]: return False, "empty reference result (vacuous)"
    if cls == "C0_column_name_control":
        if len(ref["keys"]) != len(cand["keys"]): return False, "column count differs"
        if ref["keys"] == cand["keys"]: return False, "column names unchanged"
        if sorted(rows_t(ref)) != sorted(rows_t(cand)): return False, "values differ"
        return True, {"note": "values equal; column names differ"}
    if cls == "R5_column_order":
        if len(ref["keys"]) < 2: return False, "fewer than 2 columns"
        if cand["keys"] != list(reversed(ref["keys"])) or cand["keys"] == ref["keys"]: return False, "column list not reversed"
        if len(ref["rows"]) != len(cand["rows"]): return False, "row count differs"
        if rows_t(ref) != rows_t(cand, ref["keys"]): return False, "rows differ after alignment by name"
        return True, {"columns": len(ref["keys"]), "rows": len(ref["rows"])}
    if ref["keys"] != cand["keys"]: return False, "column names differ"
    R, C = rows_t(ref), rows_t(cand)
    if cls in ("R1_numeric_type", "R2_float_tolerance", "R7_list_order"):
        if len(ref["rows"]) != len(cand["rows"]): return False, "row count differs"
        dc = diff_cols(ref, cand)
        if not dc: return False, "results identical (no differing column)"
        if len(dc) != 1: return False, "more than one column differs"
        t = dc[0]; pairs = [(a[t], b[t]) for a, b in zip(ref["rows"], cand["rows"])]
        if cls == "R1_numeric_type":
            for a, b in pairs:
                if not is_int(a): return False, "reference cell not integer"
                if not isinstance(b, float): return False, "candidate cell not float"
                if float(a) != b: return False, "numeric values differ"
            return True, {"column": t, "type_ref": "int", "type_cand": "float", "rows": len(pairs)}
        if cls == "R2_float_tolerance":
            deltas = []
            for a, b in pairs:
                if not (isinstance(a, float) and isinstance(b, float)): return False, "non-float cell"
                if math.isnan(a) or math.isnan(b): return False, "NaN"
                d = abs(b - a)
                if d > EPSILON_REL * max(1.0, abs(a)): return False, f"delta {d!r} exceeds epsilon"
                deltas.append(d)
            if not any(deltas): return False, "zero delta (exactly equal; not a tolerance case)"
            return True, {"column": t, "max_abs_delta": max(deltas), "n_nonzero": sum(1 for d in deltas if d),
                          "rows": len(pairs)}
        moved = 0
        for a, b in pairs:
            if not (isinstance(a, list) and isinstance(b, list)): return False, "non-list cell"
            if any(isinstance(x, (list, dict)) for x in a + b): return False, "nested list element"
            if sorted(cell(x) for x in a) != sorted(cell(x) for x in b): return False, "list elements differ"
            moved += [cell(x) for x in a] != [cell(x) for x in b]
        if not moved: return False, "no list sequence differs"
        return True, {"column": t, "rows": len(pairs), "rows_with_reordered_list": moved,
                      "max_list_len": max(len(a) for a, _ in pairs)}
    if cls == "R3_row_order":
        if has_order_skip_limit_anywhere(ref_q): return False, "reference has ORDER BY/SKIP/LIMIT"
        if sorted(R) != sorted(C): return False, "row multisets differ"
        if R == C: return False, "row sequence unchanged"
        return True, {"rows": len(R), "columns": len(ref["keys"])}
    if cls == "R6_reference_order":
        if count_order_by(ref_q) != 1 or re.search(r"\b(SKIP|LIMIT)\b", ref_q, re.I):
            return False, "reference not exactly one ORDER BY without SKIP/LIMIT"
        if count_order_by(cand_q) != 0: return False, "candidate has ORDER BY"
        if sorted(R) != sorted(C): return False, "row multisets differ"
        if R == C: return False, "row sequence unchanged (trigger not exercised)"
        return True, {"rows": len(R), "columns": len(ref["keys"])}
    if cls == "R4_duplicates":
        if len(set(R)) != len(R): return False, "reference has duplicate rows"
        if set(R) != set(C): return False, "distinct row sets differ"
        if len(C) == len(set(C)): return False, "candidate has no duplicates"
        seen, dedup = set(), []
        for t in C:
            if t not in seen: seen.add(t); dedup.append(t)
        if dedup != R: return False, "de-duplicated order differs from reference"
        return True, {"ref_rows": len(R), "cand_rows": len(C), "duplicate_rows": len(C) - len(R),
                      "columns": len(ref["keys"])}
    if cls == "R8_null_natural":
        if R != C: return False, "results not identical"
        cells = [r[k] for r in ref["rows"] for k in ref["keys"]]
        if not any(v is None for v in cells): return False, "no NULL in result"
        if all(v is None for v in cells): return False, "result all NULL"
        return True, {"rows": len(R), "columns": len(ref["keys"]), "null_columns": null_profile(ref)}
    return False, "unknown class"


def run_read(driver, q):
    def work(tx):
        r = tx.run(q); keys = list(r.keys()); rows = []
        for rec in r:
            try: rows.append(canon(dict(rec)))
            except TypeError as e: raise NonJSON(str(e))
        return {"keys": keys, "rows": rows}
    with driver.session() as s:
        return s.execute_read(work)


def fingerprint(driver):
    with driver.session() as s:
        nodes = s.run("MATCH (n) RETURN labels(n) AS l, properties(n) AS p").data()
        rels = s.run("MATCH (a)-[r]->(b) RETURN type(r) AS t, properties(r) AS p, elementId(a) AS a, elementId(b) AS b").data()
        labels = s.run("MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS c ORDER BY l").data()
        types = s.run("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY t").data()
    blob = json.dumps(sorted(json.dumps(x, sort_keys=True, default=str) for x in nodes + rels))
    return {"nodes": len(nodes), "relationships": len(rels), "sha256": hashlib.sha256(blob.encode()).hexdigest(),
            "label_counts": {x["l"]: x["c"] for x in labels}, "rel_type_counts": {x["t"]: x["c"] for x in types}}


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def evaluate(c, run):
    """run(query) -> result. Returns (pass, reason_or_detail, ref, cand)."""
    rq, cq = c["reference_cypher"], c["candidate_cypher"]
    if looks_sql(rq) or looks_sql(cq): return False, "SQL-looking text", None, None
    if rq == cq: return False, "identical query text", None, None
    try:
        r1, r2 = run(rq), run(rq)
        c1, c2 = run(cq), run(cq)
    except NonJSON as e:
        return False, f"graph/temporal value: {str(e)[:120]}", None, None
    except Exception as e:
        return False, f"execution error: {type(e).__name__}: {str(e)[:150]}", None, None
    if r1 != r2 or c1 != c2: return False, "non-deterministic result", r1, c1
    if max(len(r1["rows"]), len(c1["rows"])) > MAX_ROWS: return False, "too many rows", None, None
    ok, det = check(c["class"], r1, c1, rq, cq)
    return ok, det, r1, c1


def eval_graph(cand_path, graph, uri, user, pw, work, dump_path):
    from neo4j import GraphDatabase
    import neo4j
    cands = [json.loads(l) for l in open(cand_path) if json.loads(l)["graph"] == graph]
    driver = GraphDatabase.driver(uri, auth=(user, pw))
    server = driver.get_server_info().agent
    before = fingerprint(driver)
    if before["nodes"] == 0: raise SystemExit(f"graph {graph} is empty: load failed")
    results = []
    for c in sorted(cands, key=lambda c: (c["class"], c["rank"], c["sub_rank"])):
        ok, det, r1, c1 = evaluate(c, lambda q: run_read(driver, q))
        results.append({**c, "oracle_pass": ok, "oracle_reason": det if isinstance(det, str) else "PASS",
                        "oracle_detail": det if isinstance(det, dict) else None, "reference": r1, "candidate": c1})
    after = fingerprint(driver)
    driver.close()
    if before != after: raise SystemExit(f"graph changed during read-only oracle: {graph}")
    os.makedirs(work, exist_ok=True)
    json.dump({"graph": graph, "neo4j_server": server, "neo4j_python_driver": neo4j.__version__,
               "dump_file": os.path.basename(dump_path), "dump_sha256": sha(dump_path),
               "fingerprint": before, "fingerprint_after_queries_sha256": after["sha256"], "unchanged": True,
               "results": results}, open(os.path.join(work, f"{graph}.json"), "w"), default=str)
    print(json.dumps({"graph": graph, "server": server, "nodes": before["nodes"], "rels": before["relationships"],
                      "evaluated": len(results), "passed": sum(r["oracle_pass"] for r in results)}))


def select(results):
    """first passing variant per source; first QUOTA passing sources per class (generator order). As S20."""
    admitted, rejected = [], []
    for cls in sorted({r["class"] for r in results}):
        n, by_rank = 0, {}
        for r in sorted([r for r in results if r["class"] == cls], key=lambda r: (r["rank"], r["sub_rank"])):
            by_rank.setdefault(r["rank"], []).append(r)
        for rank in sorted(by_rank):
            chosen = None
            for r in by_rank[rank]:
                if r["oracle_pass"] and chosen is None and n < QUOTA[cls]: chosen = r
                elif r["oracle_pass"] and chosen is None: rejected.append({**r, "oracle_reason": "RESERVE_NOT_ADMITTED (quota met)"})
                elif r["oracle_pass"]: rejected.append({**r, "oracle_reason": "FALLBACK_NOT_NEEDED (earlier variant admitted)"})
                else: rejected.append(r)
            if chosen: n += 1; admitted.append(chosen)
    return admitted, rejected


def freeze(cand_path, work, prereg_dir, out_base):
    for l in open(os.path.join(prereg_dir, "hashes.sha256")):
        h, fn = l.split()
        assert sha(os.path.join(prereg_dir, fn)) == h, f"preregistration freeze violated: {fn}"
    prereg = json.load(open(os.path.join(prereg_dir, "preregistration.json")))
    assert prereg["candidates_sha256"] == sha(cand_path), "candidates changed after preregistration"
    for name, h in prereg["code_sha256"].items():
        assert sha(os.path.join(HERE, name)) == h, f"code changed after preregistration: {name}"
    graphs = sorted({json.loads(l)["graph"] for l in open(cand_path)})
    per = {g: json.load(open(os.path.join(work, f"{g}.json"))) for g in graphs}
    results = [r for g in graphs for r in per[g]["results"]]
    admitted, rejected = select(results)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = os.path.join(out_base, f"{stamp}_input"); os.makedirs(out)

    def side(q, res): return {"query": q, "columns": res["keys"], "rows": [[row[k] for k in res["keys"]] for row in res["rows"]]}
    with open(os.path.join(out, "cases.jsonl"), "w") as f:
        for r in admitted:
            f.write(json.dumps({"case_id": r["case_id"],
                "reference": side(r["reference_cypher"], r["reference"]),
                "prediction": side(r["candidate_cypher"], r["candidate"]),
                "meta": {"family": r["class"], "equivalence_class": r["equivalence_class"], "rule": r["rule"],
                         "graph": r["graph"], "source_id": r["source_id"], "source_file": r["source_file"],
                         "controlled_fixture": False, "oracle_detail": r["oracle_detail"],
                         "source_gold_cypher": r["source_gold_cypher"],
                         "source_gold_cypher_raw": r["source_gold_cypher_raw"]}}) + "\n")
    fields = ["case_id", "class", "equivalence_class", "rule", "rank", "sub_rank", "graph", "source_id", "source_file",
              "oracle_reason", "reference_cypher", "candidate_cypher"]
    for name, rows in [("case_manifest.csv", admitted), ("rejections.csv", rejected)]:
        with open(os.path.join(out, name), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    json.dump({"oracle_version": "s23-oracle-v1", "oracle_definitions": ORACLE_DEFS, "max_rows": MAX_ROWS,
               "sources_attempted_per_class": Counter(r["class"] for r in results if r["sub_rank"] == 0),
               "variants_attempted_per_class": Counter(r["class"] for r in results),
               "admitted_per_class": Counter(r["class"] for r in admitted),
               "admitted_per_class_graph": {c: Counter(r["graph"] for r in admitted if r["class"] == c) for c in CLASSES},
               "rejected_reasons_per_class": {c: Counter(r["oracle_reason"].split(":")[0] for r in rejected if r["class"] == c)
                                              for c in CLASSES},
               "admitted_detail": {r["case_id"]: r["oracle_detail"] for r in admitted},
               "every_admitted_query_executed_twice_identically": True,
               "frozen_utc": stamp, "status": "FROZEN BEFORE ANY SCORER RUN"},
              open(os.path.join(out, "oracle_checks.json"), "w"), indent=2, default=dict)
    json.dump({g: {k: v for k, v in per[g].items() if k != "results"} for g in graphs},
              open(os.path.join(out, "graph_manifest.json"), "w"), indent=2, default=str)
    json.dump({"classes": CLASSES, "quota": QUOTA, "epsilon_rel": EPSILON_REL,
               "epsilon_rule": "0 < |cand - ref| <= epsilon_rel * max(1, |ref|)", "oracle_definitions": ORACLE_DEFS,
               "label_note": "Equivalence classes are declared, not claims that either result is 'correct'. "
                             "R4 is SET_EQUIVALENT_MULTISET_DIFFERENT (not universally equivalent); R5 COLUMN_ORDER_POLICY, "
                             "R6 REFERENCE_ORDERED_CANDIDATE_UNORDERED and R7 LIST_ORDER_POLICY are policy-profiling "
                             "classes (intent-dependent); R8 uses naturally occurring NULLs only; C0 is a calibration "
                             "control, not new evidence."},
              open(os.path.join(out, "equivalence_policy.json"), "w"), indent=2)
    src = dict(prereg["source"]); src.update({"candidates_file_sha256": sha(cand_path),
               "preregistration_dir": os.path.relpath(prereg_dir, ROOT),
               "preregistration_hashes_sha256": sha(os.path.join(prereg_dir, "hashes.sha256"))})
    json.dump(src, open(os.path.join(out, "source_manifest.json"), "w"), indent=2)
    open(os.path.join(out, "README_FINALIZATION.txt"), "w").write(
        f"study S23 cross-benchmark replication on Mind the Query: INPUT freeze {stamp}. Cases admitted by the "
        f"execution oracle on an isolated throwaway Neo4j ({', '.join(sorted({per[g]['neo4j_server'] for g in graphs}))}). "
        f"No scorer has seen these cases. Replication criterion frozen earlier in {os.path.relpath(prereg_dir, ROOT)}. "
        f"Do not edit.\n")
    lines = [f"{sha(os.path.join(out, fn))}  {fn}" for fn in sorted(os.listdir(out))]
    open(os.path.join(out, "hashes.sha256"), "w").write("\n".join(lines) + "\n")
    print(json.dumps({"frozen": out, "admitted": dict(Counter(r["class"] for r in admitted)), "rejected": len(rejected),
                      "hashes_sha256": sha(os.path.join(out, "hashes.sha256"))}))


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "eval-graph": eval_graph(*sys.argv[2:9])
    elif mode == "freeze": freeze(*sys.argv[2:6])
    else: raise SystemExit("mode: eval-graph | freeze")
