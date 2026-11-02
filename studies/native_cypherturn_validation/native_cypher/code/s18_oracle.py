#!/usr/bin/env python3
"""study S18 oracle validator + input freeze (s18-oracle-v1). Requires a running, ISOLATED Neo4j (see run_s18_oracle.sh).

For each CypherTurn graph: clear the isolated database, load the released data.cypher, fingerprint the graph, then run
every candidate's reference (gold) and rewrite query twice read-only and apply the family's oracle rule:
  T1/T2  SCHEMA_EQUIVALENT_BY_DECLARED_POLICY  same number of columns; value tuples equal (multiset; also as a sequence
         when the final clauses order rows); only column names differ
  T4     VALUE_EQUIVALENT                      reference rows contain no duplicates AND rewrite result identical
  T5     VALUE_EQUIVALENT                      identical column names and rows, types included (repr-level)
Exclusions (pre-declared): execution error/timeout; non-deterministic result across two runs; empty reference result
(vacuous); graph-object or temporal values (not JSON-level); > 5,000 rows. First QUOTA passing candidates per family
(by generator rank) are admitted; the rest are logged. Writes the frozen input package; NO scorer is touched.
  python s18_oracle.py <candidates.jsonl> <cypherturn_dir> <bolt_uri> <user> <password> <out_base_dir>
"""
import csv, datetime, hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s18_rewrite import QUOTA, parse_return

MAX_ROWS = 5000

def canon(v):
    if v is None or isinstance(v, (bool, int, float, str)): return v
    if isinstance(v, list): return [canon(x) for x in v]
    if isinstance(v, dict): return {k: canon(x) for k, x in v.items()}
    raise TypeError(f"non-JSON value {type(v).__name__}")

def tuples(res):
    return [tuple(json.dumps(r[k], sort_keys=True) + "|" + type(r[k]).__name__ for k in res["keys"]) for r in res["rows"]]

def ordered(q):
    p = parse_return(q)
    return bool(p and any(t.strip().upper().startswith("ORDER BY") for t in p[3]))

def oracle(family, ref, cand, ref_q):
    """-> (admit: bool, classification, reason)."""
    if not ref["rows"]: return False, "NOT_SAFE_TO_INCLUDE", "empty reference result (vacuous)"
    rt, ct = tuples(ref), tuples(cand)
    same_multiset = sorted(rt) == sorted(ct)
    same_seq = rt == ct
    if ordered(ref_q) and not same_seq: return False, "NOT_SAFE_TO_INCLUDE", "ordered result sequence differs"
    if family in ("T1_alias_rename", "T2_drop_alias"):
        if len(ref["keys"]) != len(cand["keys"]): return False, "NOT_SAFE_TO_INCLUDE", "column count differs"
        if ref["keys"] == cand["keys"]: return False, "NOT_SAFE_TO_INCLUDE", "column names unchanged"
        if not same_multiset: return False, "NOT_SAFE_TO_INCLUDE", "values differ"
        return True, "SCHEMA_EQUIVALENT_BY_DECLARED_POLICY", "values equal; column names differ"
    if family == "T4_add_distinct":
        if len(set(rt)) != len(rt): return False, "NOT_SAFE_TO_INCLUDE", "reference has duplicate rows"
        if ref["keys"] != cand["keys"] or not same_multiset: return False, "NOT_SAFE_TO_INCLUDE", "result differs"
        return True, "VALUE_EQUIVALENT", "duplicate-free reference; identical result"
    if family == "T5_numeric_literal":
        if ref["keys"] != cand["keys"] or not same_multiset: return False, "NOT_SAFE_TO_INCLUDE", "result differs"
        return True, "VALUE_EQUIVALENT", "identical result incl. types"
    return False, "NOT_SAFE_TO_INCLUDE", "unknown family"

def run_read(driver, q):
    def work(tx):
        r = tx.run(q)
        keys = list(r.keys())
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
        # Load exactly as CypherTurn's scripts/import_graphs.py: clear, split on ';', run each non-empty statement,
        # warn-and-skip on failure (failures counted and recorded).
        failed = 0
        with driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n").consume()       # isolated S18 container only
            stmts = [x.strip() for x in open(data, encoding="utf-8").read().split(";") if x.strip()]
            for st in stmts:
                try:
                    s.run(st).consume()
                except Exception:
                    failed += 1
        fps[graph] = {**fingerprint(driver), "data_cypher_sha256": sha(data), "statements": len(stmts),
                      "failed_statements": failed, "loader": "CypherTurn scripts/import_graphs.py semantics"}
        for c in sorted([c for c in cands if c["graph"] == graph], key=lambda c: (c["family"], c["rank"])):
            rec = {**c}
            try:
                r1, r2 = run_read(driver, c["gold_cypher"]), run_read(driver, c["gold_cypher"])
                c1, c2 = run_read(driver, c["rewrite_cypher"]), run_read(driver, c["rewrite_cypher"])
                if r1 != r2 or c1 != c2: ok, cls, why = False, "NOT_SAFE_TO_INCLUDE", "non-deterministic result"
                elif max(len(r1["rows"]), len(c1["rows"])) > MAX_ROWS: ok, cls, why = False, "NOT_SAFE_TO_INCLUDE", "too many rows"
                else: ok, cls, why = oracle(c["family"], r1, c1, c["gold_cypher"])
                rec.update(reference=r1, candidate=c1)
            except Exception as e:
                ok, cls, why = False, "NOT_SAFE_TO_INCLUDE", f"execution error: {type(e).__name__}: {str(e)[:150]}"
            rec.update(oracle_pass=ok, oracle_class=cls, oracle_reason=why)
            results.append(rec)
    driver.close()
    admitted, rejected = [], []
    for fam in sorted({r["family"] for r in results}):
        n = 0
        for r in sorted([r for r in results if r["family"] == fam], key=lambda r: r["rank"]):
            if r["oracle_pass"] and n < QUOTA: n += 1; admitted.append(r)
            else: rejected.append({**r, "oracle_reason": r["oracle_reason"] if not r["oracle_pass"] else "RESERVE_NOT_ADMITTED (quota met)"})
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = os.path.join(out_base, f"{stamp}_native_cypher_input"); os.makedirs(out)
    with open(os.path.join(out, "cases.jsonl"), "w") as f:
        for r in admitted:
            f.write(json.dumps({"case_id": r["case_id"],
                "reference": {"query": r["gold_cypher"], "columns": r["reference"]["keys"],
                              "rows": [[row[k] for k in r["reference"]["keys"]] for row in r["reference"]["rows"]]},
                "prediction": {"query": r["rewrite_cypher"], "columns": r["candidate"]["keys"],
                               "rows": [[row[k] for k in r["candidate"]["keys"]] for row in r["candidate"]["rows"]]},
                "meta": {"family": r["family"], "graph": r["graph"], "session_id": r["session_id"], "turn_id": r["turn_id"],
                         "oracle_class": r["oracle_class"], "cluster": r["graph"] + "|" + r["gold_cypher"]}}) + "\n")
    fields = ["case_id", "family", "rank", "graph", "session_id", "turn_id", "oracle_class", "oracle_reason", "gold_cypher", "rewrite_cypher"]
    for name, rows in [("transformations.csv", admitted), ("rejections.csv", rejected)]:
        with open(os.path.join(out, name), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    from collections import Counter
    json.dump({"oracle_version": "s18-oracle-v1", "quota_per_family": QUOTA, "max_rows": MAX_ROWS,
               "admitted_per_family": Counter(r["family"] for r in admitted),
               "rejected_reasons": Counter(r["oracle_reason"].split(":")[0] for r in rejected),
               "T3_column_reorder": "NOT FEASIBLE: no CypherTurn gold query returns more than one column",
               "neo4j_server": server, "neo4j_python_driver": neo4j.__version__, "graph_fingerprints": fps,
               "frozen_utc": stamp, "status": "FROZEN BEFORE ANY SCORER RUN"},
              open(os.path.join(out, "oracle_manifest.json"), "w"), indent=2, default=dict)
    ct_commit = os.popen(f"git -C '{ct_dir}' rev-parse HEAD").read().strip()
    json.dump({"source": "BarryQ/CypherTurn", "commit": ct_commit, "licence_note": "README: released for research purposes; no licence file",
               "scenario_files_sha256": {os.path.basename(p): sha(os.path.join(ct_dir, "data", "scenarios", p))
                                         for p in sorted(os.listdir(os.path.join(ct_dir, "data", "scenarios")))},
               "candidates_file_sha256": sha(cand_path),
               "generator_sha256": sha(os.path.join(os.path.dirname(os.path.abspath(__file__)), "s18_rewrite.py")),
               "oracle_sha256": sha(os.path.abspath(__file__))}, open(os.path.join(out, "source_manifest.json"), "w"), indent=2)
    open(os.path.join(out, "README_FINALIZATION.txt"), "w").write(
        f"study S18 post-freeze native-Cypher validation: INPUT freeze {stamp}. Cases admitted by execution oracle on "
        f"isolated Neo4j ({server}). No scorer has seen these cases. Do not edit.\n")
    lines = [f"{sha(os.path.join(out, fn))}  {fn}" for fn in sorted(os.listdir(out))]
    open(os.path.join(out, "hashes.sha256"), "w").write("\n".join(lines) + "\n")
    print(json.dumps({"frozen": out, "admitted": len(admitted), "rejected": len(rejected),
                      "hashes_sha256": sha(os.path.join(out, "hashes.sha256"))}))

if __name__ == "__main__":
    main()
