#!/usr/bin/env python3
"""S49 (APPROVAL-BOUND, prepared only): execute every Mind the Query manual test-split gold query once, read-only, on
the graph already loaded in the server at URI, and store the rows for result-level exposure.

  execute_mtq_gold.py <graph> <uri> <user> <password> <out.jsonl>

Each row is written as JSON in column order; nodes/relationships/paths become {"__graph_object__": <kind>} so they count as
JSON-object cells (PROTOCOL.md: maps and graph objects are not separated); temporal values become strings.
A query error or a 60 s timeout is recorded as {"error": ...} and never retried.
"""
import glob
import json
import os
import sys

import neo4j

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))


def cell(v):
    if isinstance(v, (neo4j.graph.Node, neo4j.graph.Relationship, neo4j.graph.Path)):
        return {"__graph_object__": type(v).__name__}
    if isinstance(v, list):
        return [cell(x) for x in v]
    if isinstance(v, dict):
        return {k: cell(x) for k, x in v.items()}
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


def main(graph, uri, user, pw, out):
    files = sorted(glob.glob(os.path.join(ROOT, f"external/mind_the_query/Train_Test_Splits/Manual/{graph}/test/*.json")))
    drv = neo4j.GraphDatabase.driver(uri, auth=(user, pw))
    with open(out, "a") as fh:
        for p in files:
            for r in json.load(open(p)):
                q = (r.get("Cypher") or "").strip()
                if not q:
                    continue
                rec = {"graph": graph, "item_id": r["unique_id"], "query": q}
                try:
                    with drv.session() as s:
                        def work(tx):
                            res = tx.run(neo4j.Query(q, timeout=60))
                            keys = list(res.keys())
                            return keys, [{k: cell(x[k]) for k in keys} for x in res]
                        keys, rows = s.execute_read(work)
                    rec.update({"columns": keys, "rows": rows})
                except Exception as e:  # recorded, never retried
                    rec["error"] = f"{type(e).__name__}: {str(e)[:300]}"
                fh.write(json.dumps(rec) + "\n")
    drv.close()


if __name__ == "__main__":
    main(*sys.argv[1:6])
