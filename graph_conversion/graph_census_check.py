#!/usr/bin/env python3
"""Compare a loaded Neo4j graph with the frozen G0 fingerprint (per-label node counts; per "TYPE|From->To" relationship
counts). Read-only queries.  [NEO4J_URI=...] [NEO4J_PASSWORD=...] python3 graph_census_check.py"""
import json, os, sys
from neo4j import GraphDatabase
exp = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "expected_G0_fingerprint.json")))
pw = os.environ.get("NEO4J_PASSWORD")  # leave unset for a throwaway container started with auth disabled
auth = None if pw is None else (os.environ.get("NEO4J_USERNAME", "neo4j"), pw)
d = GraphDatabase.driver(os.environ.get("NEO4J_URI", "bolt://localhost:7687"), auth=auth)
with d.session() as s:
    nodes = {r["l"]: r["c"] for r in s.run("MATCH (n) RETURN labels(n)[0] AS l, count(*) AS c")}
    rels = {f"{r['t']}|{r['a']}->{r['b']}": r["c"] for r in
            s.run("MATCH (a)-[r]->(b) RETURN type(r) AS t, labels(a)[0] AS a, labels(b)[0] AS b, count(*) AS c")}
d.close()
nd = {k: (nodes.get(k, 0), exp["nodes"].get(k, 0)) for k in set(nodes) | set(exp["nodes"]) if nodes.get(k, 0) != exp["nodes"].get(k, 0)}
rd = {k: (rels.get(k, 0), exp["rels"].get(k, 0)) for k in set(rels) | set(exp["rels"]) if rels.get(k, 0) != exp["rels"].get(k, 0)}
print(json.dumps({"node_differences": nd, "relationship_differences": rd}, indent=1))
print("GRAPH CENSUS:", "MATCHES G0" if not nd and not rd else "DIFFERS from G0")
sys.exit(0 if not nd and not rd else 1)
