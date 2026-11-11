#!/usr/bin/env python3
"""Minimal cases for the CypherBench reflexivity observation of paper Section IV (executed after the frozen runs).

CypherBench's `to_hashable(..., unorder_list=True)` sorts list values. A list that Python cannot sort (a NULL beside a
number, mixed types, maps with a missing property) raises TypeError inside `execution_accuracy`, which catches it on the
prediction side and returns 0.0. Two identical results are therefore rejected when the query texts differ.

Runs the pinned CypherBench scorer (fetch it first: bash third_party/fetch_scorers.sh) through the frozen adapter of
studies/adapter_readiness/, on frozen rows; no database, no network.
usage: python3 studies/posthoc_minimal_cases/cypherbench_unsortable_list.py   (in the scorer environment, environment/)"""
import json, sys
from pathlib import Path
ART = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ART / "studies/adapter_readiness/audit_readiness/code"))
import audit_adapters as A


def pair(cid, rq, pq, rows_ref, rows_pred, col="l"):
    return {"case_id": cid, "reference": {"query": rq, "columns": [col], "rows": rows_ref},
            "prediction": {"query": pq, "columns": [col], "rows": rows_pred}}


Q1, Q2 = "MATCH (x) RETURN [x.a, x.b] AS l", "MATCH (y) RETURN [y.a, y.b] AS l"
M = [{"name": "a", "age": None}, {"name": "a", "age": 30}]
CASES = [  # (pair, expected verdict: 1 accept, 0 reject, "E" exception)
    (pair("identical_list_with_null", Q1, Q2, [[[1, None]]], [[[1, None]]]), 0),
    (pair("identical_list_mixed_types", Q1, Q2, [[[1, "a"]]], [[[1, "a"]]]), 0),
    (pair("identical_list_of_maps_missing_property", "MATCH (p:P) RETURN collect(p {.name, .age}) AS l",
          "MATCH (q:P) RETURN collect(q {.name, .age}) AS l", [[M]], [[M]]), 0),
    (pair("identical_sortable_list_control", Q1, Q2, [[[1, 2]]], [[[1, 2]]]), 1),
    (pair("identical_list_with_null_same_text", Q1, Q1, [[[1, None]]], [[[1, None]]]), 1),   # identical-text shortcut
    (pair("unsortable_list_on_reference_side_only", Q1, "MATCH (y) RETURN [y.a, y.c] AS l", [[[1, None]]], [[[1, 2]]]), "E"),
]
score = A.LOADERS["cypherbench"]()
ok = True; out = []
for p, want in CASES:
    try:
        got = score(p)[1]
    except Exception as e:
        got = "E"; p["exception"] = type(e).__name__
    ok &= got == want
    out.append({"case": p["case_id"], "verdict": got, "expected": want, "exception": p.get("exception")})
    print(("OK  " if got == want else "FAIL"), p["case_id"], "->", got, p.get("exception", ""))
exp = Path(__file__).with_name("expected_cypherbench_unsortable_list.json")
if "--write-expected" in sys.argv:
    exp.write_text(json.dumps(out, indent=1) + "\n")
elif exp.exists():
    ok &= json.loads(exp.read_text()) == out
print("RESULT:", "PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
