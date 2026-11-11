#!/usr/bin/env python3
"""Minimal cases for the integer-versus-float row pre-check of paper Section VI (corpus pair S3-473).

CypherBench and GQLBench inherit `unorder_row` from the Spider test-suite evaluator: each row is sorted by
`str(value) + str(type(value))` before `quick_rej` compares the rows. `21` and `21.0` can then land in different
positions of a multi-column row, so two results whose rows are equal in sequence are rejected, although the same pair
of values in a single-column result is accepted.

Runs the pinned scorers (fetch first: bash third_party/fetch_scorers.sh) through the frozen adapters of
studies/adapter_readiness/, on frozen rows; no database, no network.
usage: python3 studies/posthoc_minimal_cases/row_precheck_int_float.py   (in the scorer environment, environment/)"""
import json, sys
from pathlib import Path
ART = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ART / "studies/adapter_readiness/audit_readiness/code"))
import audit_adapters as A


def pair(cid, cols, rows_ref, rows_pred):
    q = ", ".join("x.%s AS %s" % (c, c) for c in cols)
    return {"case_id": cid, "reference": {"query": "MATCH (x) RETURN " + q, "columns": cols, "rows": rows_ref},
            "prediction": {"query": "MATCH (y) RETURN " + q.replace("x.", "y."), "columns": cols, "rows": rows_pred}}


CASES = [  # (pair, expected verdict of both scorers)
    (pair("one_column_21_vs_21.0", ["d"], [[21]], [[21.0]]), 1),
    (pair("two_columns_210_21_vs_210_21.0", ["id", "d"], [[210, 21]], [[210, 21.0]]), 0),
    (pair("two_columns_identical_types_control", ["id", "d"], [[210, 21]], [[210, 21]]), 1),
]
ok = True; out = []
for name in ("cypherbench", "gqlbench"):
    score = A.LOADERS[name]()
    for p, want in CASES:
        got = score(p)[1]
        ok &= got == want
        out.append({"scorer": name, "case": p["case_id"], "verdict": got, "expected": want})
        print(("OK  " if got == want else "FAIL"), name, p["case_id"], "->", got)
key = lambda row: tuple(sorted(row, key=lambda x: str(x) + str(type(x))))
print("sort key demo:", key((210, 21)), "vs", key((210, 21.0)))
exp = Path(__file__).with_name("expected_row_precheck_int_float.json")
if "--write-expected" in sys.argv:
    exp.write_text(json.dumps(out, indent=1) + "\n")
elif exp.exists():
    ok &= json.loads(exp.read_text()) == out
print("RESULT:", "PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
