#!/usr/bin/env python3
"""Regenerate the stored SQL and Cypher outputs of the 563 corpus records and compare them with the released ones.

  python3 regenerate_outputs.py RECORDS.jsonl WORKS_CYCLES.sqlite [--neo4j]      (> regeneration_report.json)

RECORDS.jsonl: the dataset repository's corpus/records_release_candidate.jsonl (fields SQL, cypher, sql_output,
neo4j_output). SQL side: each gold SQL query runs on the SQLite file opened read-only (60 s limit). Cypher side
(--neo4j; $NEO4J_URI, $NEO4J_USERNAME, $NEO4J_PASSWORD): each gold Cypher query runs read-only on the graph built by
insert_to_neo4j.py, rows taken as the Neo4j driver returns them (`result.data()`, 60 s limit).
Comparison: EXACT = same rows in the same order; MULTISET = same rows, different order (expected for queries without
ORDER BY and for ties, since row order is not defined there); DIFFERENT otherwise. Values are compared after JSON
round-tripping (as stored) with integers and integral floats treated alike. The stored SQL outputs are lists of
dictionaries keyed by column name, so a result with two columns of the same name was stored with one of them; the SQL
side is therefore also compared after the same dictionary serialisation ("as_serialised"). Nothing is modified."""
import collections, json, math, os, sqlite3, sys, time


def norm(v):
    if isinstance(v, bool): return v
    if isinstance(v, (int, float)):
        f = float(v); return int(f) if math.isfinite(f) and f.is_integer() else f
    if isinstance(v, list): return tuple(norm(x) for x in v)
    if isinstance(v, dict): return tuple(sorted((k, norm(x)) for k, x in v.items()))
    return v


def rows_of(dicts):
    return [tuple((k, norm(v)) for k, v in d.items()) for d in (dicts or [])]


def compare(got, exp):
    if got == exp: return "EXACT"
    if collections.Counter(got) == collections.Counter(exp): return "MULTISET"
    return "DIFFERENT"


def main():
    if len(sys.argv) < 3: sys.exit(__doc__)
    recs = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
    con = sqlite3.connect(f"file:{sys.argv[2]}?mode=ro", uri=True)
    report = {"records": len(recs), "sql": collections.Counter(), "sql_as_serialised": collections.Counter(), "sql_examples": []}
    for r in recs:
        deadline = time.time() + 60
        con.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 10000)
        try:
            cur = con.execute(r["SQL"]); cols = [d[0] for d in cur.description]; raw = cur.fetchall()
        except Exception as e:
            report["sql"]["ERROR"] += 1; report["sql_as_serialised"]["ERROR"] += 1
            report["sql_examples"].append([r["record_id"], f"error {type(e).__name__}"]); continue
        exp = rows_of(r.get("sql_output"))
        raw_rows = [tuple(zip(cols, (norm(v) for v in row))) for row in raw]
        ser_rows = rows_of([json.loads(json.dumps(dict(zip(cols, row)))) for row in raw])  # dict: duplicate names collapse
        a, b = compare(raw_rows, exp), compare(ser_rows, exp)
        report["sql"][a] += 1; report["sql_as_serialised"][b] += 1
        if a != "EXACT": report["sql_examples"].append([r["record_id"], f"raw {a}, as serialised {b}, columns {cols}"])
    if "--neo4j" in sys.argv:
        from neo4j import GraphDatabase, Query
        pw = os.environ.get("NEO4J_PASSWORD")
        auth = None if pw is None else (os.environ.get("NEO4J_USERNAME", "neo4j"), pw)
        drv = GraphDatabase.driver(os.environ.get("NEO4J_URI", "bolt://localhost:7687"), auth=auth,
                                   notifications_min_severity="OFF")  # deprecation/unknown-label notices are not results
        report["cypher"] = collections.Counter(); report["cypher_examples"] = []
        with drv.session(default_access_mode="READ") as s:
            for r in recs:
                try:
                    got = rows_of(json.loads(json.dumps(s.run(Query(r["cypher"], timeout=60)).data(), default=str)))
                except Exception as e:
                    report["cypher"]["ERROR"] += 1; report["cypher_examples"].append([r["record_id"], f"error {type(e).__name__}: {str(e)[:120]}"]); continue
                c = compare(got, rows_of(r.get("neo4j_output"))); report["cypher"][c] += 1
                if c == "DIFFERENT": report["cypher_examples"].append([r["record_id"], f"{len(got)} vs {len(r.get('neo4j_output') or [])} rows"])
        drv.close()
    print(json.dumps(report, indent=1, default=dict))


if __name__ == "__main__":
    main()
