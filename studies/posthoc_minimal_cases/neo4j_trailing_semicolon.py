#!/usr/bin/env python3
"""Checks that Neo4j 5.15.0 executes a query that ends in one semicolon (paper Section VII, "Limits").

Start an EMPTY throwaway server first (no project or benchmark data is involved):
  docker run --rm -d --name semicolon-probe -p 127.0.0.1:17687:7687 -e NEO4J_AUTH=none neo4j:5.15.0
  python3 studies/posthoc_minimal_cases/neo4j_trailing_semicolon.py        # needs the `neo4j` Python driver
  docker stop semicolon-probe
Observed on Neo4j 5.15.0 Community with driver 5.26.0: the three single-statement queries return their rows and the
two-statement text raises CypherSyntaxError ("Expected exactly one statement per query but got: 2")."""
import sys
from neo4j import GraphDatabase
uri = sys.argv[1] if len(sys.argv) > 1 else "bolt://127.0.0.1:17687"
EXPECT = [("RETURN 1 AS x", [{"x": 1}]), ("RETURN 1 AS x;", [{"x": 1}]), ("RETURN 1 AS x ;  ", [{"x": 1}]),
          ("UNWIND [1,2] AS n RETURN n;", [{"n": 1}, {"n": 2}]), ("RETURN 1 AS x; RETURN 2 AS y", "CypherSyntaxError")]
ok = True
with GraphDatabase.driver(uri) as d, d.session() as s:
    print("server:", d.get_server_info().agent)
    for q, want in EXPECT:
        try:
            got = [r.data() for r in s.run(q)]
        except Exception as e:
            got = type(e).__name__
        ok &= got == want
        print(("OK  " if got == want else "FAIL"), repr(q), "->", got)
print("RESULT:", "PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
