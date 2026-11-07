#!/usr/bin/env python3
"""Code-path check: does an ORDER BY that appears only in an intermediate WITH make CypherBench and
GQLBench compare row order? Takes the first CypherTurn gold turn (sorted scenario files) whose query contains
'order by' inside a WITH and whose gold answer has >= 3 distinct rows, and scores (a) the same rows reversed and
(b) the same rows in the same order, through the frozen audit adapters. The candidate text is the reference text plus a
Cypher comment, so replay can tell the sides apart and no identical-text shortcut applies. Deterministic, no database."""
import glob
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(ROOT, "studies/adapter_readiness/audit_readiness/code"))
import audit_adapters as K  # noqa: E402

ex = None
for p in sorted(glob.glob(os.path.join(ROOT, "external/cypherturn/data/scenarios/*_sessions.json"))):
    for s in json.load(open(p)):
        for t in s["turns"]:
            q, a = t.get("gold_cypher") or "", t.get("gold_answer") or []
            if "order by" in q.lower() and "WITH" in q and len(a) >= 3 and len({json.dumps(r) for r in a}) == len(a):
                ex = (s["graph"], s["session_id"], t["turn_id"], q, a)
                break
        if ex: break
    if ex: break
graph, sid, tid, q, a = ex
cols = list(a[0].keys())
rows = [[r[c] for c in cols] for r in a]
import hashlib  # noqa: E402
out = {"graph": graph, "session_id": sid, "turn_id": tid, "reference_query_sha256": hashlib.sha256(q.encode()).hexdigest(),
       "rows": len(rows), "verdicts": {}}  # CypherTurn content is not redistributed: the query is stored as a hash
for label, cand in (("reversed", rows[::-1]), ("same_order", rows)):
    pair = {"case_id": "with-orderby-" + label, "reference": {"query": q, "columns": cols, "rows": rows},
            "prediction": {"query": q + "\n// candidate", "columns": cols, "rows": cand}}
    out["verdicts"][label] = {n: K.LOADERS[n]()(pair)[1] for n in
                              ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cyspider"]}
json.dump(out, open(os.path.join(os.path.dirname(__file__), "result.json"), "w"), indent=1)
print(json.dumps(out["verdicts"]))
