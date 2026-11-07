#!/usr/bin/env python3
"""(POST HOC, descriptive): the 41 six-scorer non-unanimous corpus pairs by provenance and disagreement dimension.

Read-only recomputation from the frozen corpus-audit verdicts and the released record_splits.csv; no scorer is run.
The dimension rule reproduces the manuscript's existing classification (Section VI, "Mechanisms on the corpus"):
float (float_only_tiny_difference) > integer/float typing > numeric NULL (only GQLBench fails) > column naming alone
(only CypherTurn fails) > engine tie order (row_order_difference, rejected by CB+GQ+TG) > other.
  python3 provenance_by_dimension.py <s3_results.csv> <record_splits.csv>
"""
import csv
import json
import os
import sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
VERDICTS = os.path.join(ROOT, "studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final/s3_results.csv")
SPLITS = os.path.join(ROOT, "../text2cypher-corpus/splits/record_splits.csv")  # dataset release beside the artifact
SIX = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cyspider"]
PROV = {"R-A": "BIRD official exact (383)", "R-B": "BIRD full-file exact (81)", "R-C": "project-written (99)"}
DIMS = ["float drift", "integer vs float", "numeric NULL", "column naming", "engine tie order", "other"]


def dimension(r):
    f = set(r["features"].split(";"))
    fails = {s for s in SIX if r[s] == "0"}
    if "float_only_tiny_difference" in f: return "float drift"
    if "int_float_type_difference" in f: return "integer vs float"
    if fails == {"gqlbench"} and "null_present" in f: return "numeric NULL"
    if fails == {"cypherturn"} and "key_name_difference" in f: return "column naming"
    if "row_order_difference" in f and fails == {"cypherbench", "gqlbench", "tugraph"}: return "engine tie order"
    return "other"


def main():
    # optional arguments for the public artifact layout: <s3_results.csv> <record_splits.csv>
    verdicts, splits = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else (VERDICTS, SPLITS)
    prov = {r["record_id"]: r["provenance_class"][:3] for r in csv.DictReader(open(splits))}
    rows = list(csv.DictReader(open(verdicts)))
    non = [r for r in rows if len({r[s] for s in SIX}) > 1]
    table = Counter((dimension(r), prov["WC-" + r["case_id"].split("-")[1]]) for r in non)
    denom = Counter(prov["WC-" + r["case_id"].split("-")[1]] for r in rows)
    out = {"note": "POST HOC, descriptive; 41 six-scorer non-unanimous pairs of 563", "denominators": dict(denom),
           "table": {d: {p: table[(d, p)] for p in PROV} for d in DIMS},
           "pairs": {r["case_id"]: [dimension(r), prov["WC-" + r["case_id"].split("-")[1]]] for r in non}}
    print(json.dumps(out, indent=1))
    lines = ["| Dimension | " + " | ".join(PROV.values()) + " | total |", "|---" * (len(PROV) + 2) + "|"]
    for d in DIMS:
        c = [table[(d, p)] for p in PROV]
        lines.append(f"| {d} | " + " | ".join(map(str, c)) + f" | {sum(c)} |")
    c = [sum(table[(d, p)] for d in DIMS) for p in PROV]
    lines.append("| non-unanimous / pairs | " + " | ".join(f"{a}/{denom[p]}" for a, p in zip(c, PROV)) + f" | {sum(c)}/{len(rows)} |")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
