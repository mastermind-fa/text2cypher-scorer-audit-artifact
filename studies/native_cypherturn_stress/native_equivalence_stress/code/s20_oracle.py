#!/usr/bin/env python3
"""study S20 oracle validator + input freeze (s20-oracle-v1). Requires a running, ISOLATED Neo4j (run_s20_oracle.sh).

For each CypherTurn graph: clear the isolated database, load the released data.cypher with CypherTurn's own import
semantics (as in study S18), fingerprint the graph, run every candidate's reference and candidate query twice in
READ transactions, fingerprint again (no accidental graph change), and apply the class rule `check()` below.
Pre-declared exclusions: execution error; non-deterministic result across two runs; empty reference; graph/temporal
values; > MAX_ROWS rows; SQL-looking text on either side. For each source (rank) the first passing variant (sub_rank)
is used; the first QUOTA passing sources per class are admitted; everything else is logged with its reason.
NO scorer is imported or run here.
  python s20_oracle.py <candidates.jsonl> <cypherturn_dir> <bolt_uri> <user> <password> <out_base_dir>
"""
import csv, datetime, hashlib, json, math, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from s20_rules import QUOTA, EPSILON_REL, CLASSES

MAX_ROWS = 5000
ORACLE_DEFS = {
    "D1_numeric_type": "same column names and row count; every reference cell is an integer (not bool) and the aligned "
                       "candidate cell is a float with float(ref) == cand; row sequence equal under numeric equality",
    "D2_float_tolerance": f"same column names, row count, cell types (float) and row alignment; every aligned pair has "
                          f"|cand - ref| <= {EPSILON_REL} * max(1, |ref|); at least one pair has a non-zero difference",
    "D3_row_order": "same column names; identical rows including types as multisets (same multiplicities); row "
                    "sequences differ; reference text has no ORDER BY / SKIP / LIMIT",
    "D4_duplicates": "same column names; reference has no duplicate rows; same set of distinct rows (types included); "
                     "candidate has at least one duplicate row; candidate de-duplicated in first-occurrence order equals "
                     "the reference sequence",
    "D5_null_controlled": "results identical including column names, types, row order and NULL positions; at least one "
                          "NULL and at least one non-NULL value in the appended column",
    "D6_column_name_control": "study S18 T1 rule: same column count and value multiset; column names differ",
}


def canon(v):
    if v is None or isinstance(v, (bool, int, float, str)): return v
    if isinstance(v, list): return [canon(x) for x in v]
    if isinstance(v, dict): return {k: canon(x) for k, x in v.items()}
    raise TypeError(f"non-JSON value {type(v).__name__}")


def cell(v):  # type-aware, exact cell identity (3 != 3.0; True != 1)
    return json.dumps(v, sort_keys=True) + "|" + type(v).__name__


def rows_t(res):
    return [tuple(cell(r[k]) for k in res["keys"]) for r in res["rows"]]


def is_int(v): return isinstance(v, int) and not isinstance(v, bool)


def looks_sql(q): return bool(re.search(r"\bSELECT\b|\bFROM\b\s+\w+\s*(WHERE|JOIN|;|$)", q, re.I))


def check(cls, ref, cand, ref_q=""):
    """Pure class rule. ref/cand = {"keys": [...], "rows": [{k: v}]}. -> (admit, detail dict or reason str)."""
    if not ref["rows"]: return False, "empty reference result (vacuous)"
    if cls == "D6_column_name_control":
        if len(ref["keys"]) != len(cand["keys"]): return False, "column count differs"
        if ref["keys"] == cand["keys"]: return False, "column names unchanged"
        if sorted(rows_t(ref)) != sorted(rows_t(cand)): return False, "values differ"
        return True, {"note": "values equal; column names differ"}
    if ref["keys"] != cand["keys"]: return False, "column names differ"
    R, C = rows_t(ref), rows_t(cand)
    if cls == "D1_numeric_type":
        if len(ref["rows"]) != len(cand["rows"]): return False, "row count differs"
        for rr, cr in zip(ref["rows"], cand["rows"]):
            for k in ref["keys"]:
                a, b = rr[k], cr[k]
                if not is_int(a): return False, "reference cell not integer"
                if not isinstance(b, float): return False, "candidate cell not float"
                if float(a) != b: return False, "numeric values differ"
        return True, {"type_ref": "int", "type_cand": "float"}
    if cls == "D2_float_tolerance":
        if len(ref["rows"]) != len(cand["rows"]): return False, "row count differs"
        deltas = []
        for rr, cr in zip(ref["rows"], cand["rows"]):
            for k in ref["keys"]:
                a, b = rr[k], cr[k]
                if not (isinstance(a, float) and isinstance(b, float)): return False, "non-float cell"
                if math.isnan(a) or math.isnan(b): return False, "NaN"
                d = abs(b - a)
                if d > EPSILON_REL * max(1.0, abs(a)): return False, f"delta {d!r} exceeds epsilon"
                deltas.append(d)
        if not any(deltas): return False, "zero delta (exactly equal; not a tolerance case)"
        return True, {"max_abs_delta": max(deltas), "n_nonzero": sum(1 for d in deltas if d)}
    if cls == "D3_row_order":
        if re.search(r"\b(ORDER\s+BY|SKIP|LIMIT)\b", ref_q, re.I): return False, "reference has ORDER BY/SKIP/LIMIT"
        if sorted(R) != sorted(C): return False, "row multisets differ"
        if R == C: return False, "row sequence unchanged"
        return True, {"rows": len(R)}
    if cls == "D4_duplicates":
        if len(set(R)) != len(R): return False, "reference has duplicate rows"
        if set(R) != set(C): return False, "distinct row sets differ"
        if len(C) == len(set(C)): return False, "candidate has no duplicates"
        seen, dedup = set(), []
        for t in C:
            if t not in seen: seen.add(t); dedup.append(t)
        if dedup != R: return False, "de-duplicated order differs from reference"
        return True, {"ref_rows": len(R), "cand_rows": len(C), "duplicate_rows": len(C) - len(R)}
    if cls == "D5_null_controlled":
        if R != C: return False, "results not identical"
        col = [r["p_opt"] for r in ref["rows"]] if "p_opt" in ref["keys"] else []
        nulls = sum(v is None for v in col)
        if not nulls: return False, "no NULL in appended column"
        if nulls == len(col): return False, "appended column all NULL"
        return True, {"null_cells": nulls, "rows": len(col)}
    return False, "unknown class"


def run_read(driver, q):
    def work(tx):
        r = tx.run(q); keys = list(r.keys())
        return {"keys": keys, "rows": [canon(dict(rec)) for rec in r]}
    with driver.session() as s:
        return s.execute_read(work)


def fingerprint(driver):
    with driver.session() as s:
        nodes = s.run("MATCH (n) RETURN labels(n) AS l, properties(n) AS p").data()
        rels = s.run("MATCH (a)-[r]->(b) RETURN type(r) AS t, properties(r) AS p, properties(a) AS a, properties(b) AS b").data()
    blob = json.dumps(sorted(json.dumps(x, sort_keys=True, default=str) for x in nodes + rels))
    return {"nodes": len(nodes), "relationships": len(rels), "sha256": hashlib.sha256(blob.encode()).hexdigest()}


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def evaluate(c, run):
    """run(query) -> result. Returns (pass, reason_or_detail, ref, cand)."""
    if looks_sql(c["reference_cypher"]) or looks_sql(c["candidate_cypher"]): return False, "SQL-looking text", None, None
    try:
        r1, r2 = run(c["reference_cypher"]), run(c["reference_cypher"])
        c1, c2 = run(c["candidate_cypher"]), run(c["candidate_cypher"])
    except Exception as e:
        return False, f"execution error: {type(e).__name__}: {str(e)[:150]}", None, None
    if r1 != r2 or c1 != c2: return False, "non-deterministic result", r1, c1
    if max(len(r1["rows"]), len(c1["rows"])) > MAX_ROWS: return False, "too many rows", r1, c1
    ok, det = check(c["class"], r1, c1, c["reference_cypher"])
    return ok, det, r1, c1


def select(results):
    """first passing variant per source; first QUOTA passing sources per class (generator order)."""
    admitted, rejected = [], []
    for cls in sorted({r["class"] for r in results}):
        n = 0
        by_rank = {}
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


def main():
    cand_path, ct_dir, uri, user, pw, out_base = sys.argv[1:7]
    from neo4j import GraphDatabase
    import neo4j
    cands = [json.loads(l) for l in open(cand_path)]
    driver = GraphDatabase.driver(uri, auth=(user, pw))
    server = driver.get_server_info().agent
    results, fps = [], {}
    for graph in sorted({c["graph"] for c in cands}):
        data = os.path.join(ct_dir, "data", "graphs", graph, "data.cypher")
        failed = 0
        with driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n").consume()       # isolated S20 container only
            stmts = [x.strip() for x in open(data, encoding="utf-8").read().split(";") if x.strip()]
            for st in stmts:
                try: s.run(st).consume()
                except Exception: failed += 1
        before = fingerprint(driver)
        for c in sorted([c for c in cands if c["graph"] == graph], key=lambda c: (c["class"], c["rank"], c["sub_rank"])):
            ok, det, r1, c1 = evaluate(c, lambda q: run_read(driver, q))
            rec = {**c, "oracle_pass": ok, "oracle_reason": det if isinstance(det, str) else "PASS",
                   "oracle_detail": det if isinstance(det, dict) else None, "reference": r1, "candidate": c1}
            results.append(rec)
        after = fingerprint(driver)
        fps[graph] = {**before, "after_queries_sha256": after["sha256"], "unchanged": before == after,
                      "data_cypher_sha256": sha(data), "statements": len(stmts), "failed_statements": failed}
        if before != after: raise SystemExit(f"graph changed during read-only oracle: {graph}")
    driver.close()
    admitted, rejected = select(results)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = os.path.join(out_base, f"{stamp}_input"); os.makedirs(out)
    with open(os.path.join(out, "cases.jsonl"), "w") as f:
        for r in admitted:
            f.write(json.dumps({"case_id": r["case_id"],
                "reference": {"query": r["reference_cypher"], "columns": r["reference"]["keys"],
                              "rows": [[row[k] for k in r["reference"]["keys"]] for row in r["reference"]["rows"]]},
                "prediction": {"query": r["candidate_cypher"], "columns": r["candidate"]["keys"],
                               "rows": [[row[k] for k in r["candidate"]["keys"]] for row in r["candidate"]["rows"]]},
                "meta": {"family": r["class"], "equivalence_class": r["equivalence_class"], "rule": r["rule"],
                         "graph": r["graph"], "session_id": r["session_id"], "turn_id": r["turn_id"],
                         "controlled_fixture": r["controlled_fixture"], "oracle_detail": r["oracle_detail"],
                         "source_gold_cypher": r["source_gold_cypher"]}}) + "\n")
    fields = ["case_id", "class", "equivalence_class", "rule", "rank", "sub_rank", "graph", "session_id", "turn_id",
              "controlled_fixture", "oracle_reason", "reference_cypher", "candidate_cypher"]
    for name, rows in [("case_manifest.csv", admitted), ("rejections.csv", rejected)]:
        with open(os.path.join(out, name), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    from collections import Counter
    attempted = Counter(r["class"] for r in results if r["sub_rank"] == 0)
    json.dump({"oracle_version": "s20-oracle-v1", "oracle_definitions": ORACLE_DEFS, "max_rows": MAX_ROWS,
               "sources_attempted_per_class": attempted,
               "variants_attempted_per_class": Counter(r["class"] for r in results),
               "admitted_per_class": Counter(r["class"] for r in admitted),
               "rejected_reasons_per_class": {cls: Counter(r["oracle_reason"].split(":")[0] for r in rejected if r["class"] == cls)
                                              for cls in CLASSES},
               "admitted_detail": {r["case_id"]: r["oracle_detail"] for r in admitted},
               "neo4j_server": server, "neo4j_python_driver": neo4j.__version__, "graph_fingerprints": fps,
               "frozen_utc": stamp, "status": "FROZEN BEFORE ANY SCORER RUN"},
              open(os.path.join(out, "oracle_checks.json"), "w"), indent=2, default=dict)
    json.dump({"classes": CLASSES, "quota": QUOTA, "epsilon_rel": EPSILON_REL,
               "epsilon_rule": "0 < |cand - ref| <= epsilon_rel * max(1, |ref|)",
               "oracle_definitions": ORACLE_DEFS,
               "label_note": "D5 is a CONTROLLED FIXTURE (gold query + one appended column); D6 is a calibration "
                             "control, not new evidence; equivalence classes are declared, not claims that either "
                             "result is 'correct'"},
              open(os.path.join(out, "equivalence_policy.json"), "w"), indent=2)
    ct_commit = os.popen(f"git -C '{ct_dir}' rev-parse HEAD").read().strip()
    json.dump({"source": "BarryQ/CypherTurn", "commit": ct_commit, "licence_note": "README: released for research purposes; no licence file",
               "scenario_files_sha256": {p: sha(os.path.join(ct_dir, "data", "scenarios", p))
                                         for p in sorted(os.listdir(os.path.join(ct_dir, "data", "scenarios")))},
               "candidates_file_sha256": sha(cand_path),
               "rules_sha256": sha(os.path.join(HERE, "s20_rules.py")), "oracle_sha256": sha(os.path.abspath(__file__))},
              open(os.path.join(out, "source_manifest.json"), "w"), indent=2)
    open(os.path.join(out, "README_FINALIZATION.txt"), "w").write(
        f"study S20 post-freeze native-Cypher equivalence stress test: INPUT freeze {stamp}. Cases admitted by the "
        f"execution oracle on isolated Neo4j ({server}). No scorer has seen these cases. Do not edit.\n")
    lines = [f"{sha(os.path.join(out, fn))}  {fn}" for fn in sorted(os.listdir(out))]
    open(os.path.join(out, "hashes.sha256"), "w").write("\n".join(lines) + "\n")
    print(json.dumps({"frozen": out, "admitted": dict(Counter(r["class"] for r in admitted)), "rejected": len(rejected),
                      "hashes_sha256": sha(os.path.join(out, "hashes.sha256"))}))


if __name__ == "__main__":
    main()
