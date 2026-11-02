#!/usr/bin/env python3
"""Rebuild the S18 exclusion input needed by s20_rules.py from PUBLIC information only (reproduction check): the regenerated S18
candidates (hash-checked against the frozen candidate hash) and the 60 frozen S18 case IDs (s18_verdicts.csv).
Writes a minimal JSONL with meta.graph and reference.query per frozen S18 case — exactly the fields s20_rules reads.
  python3 scripts/s18_exclusion_from_ids.py <s18_candidates.jsonl> <out.jsonl>"""
import csv, hashlib, json, os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
cand, out = sys.argv[1:3]
src = json.load(open(os.path.join(ROOT, "studies/native_cypherturn_validation/native_cypher/frozen/20261030T083217Z_native_cypher_input/source_manifest.json")))
assert hashlib.sha256(open(cand, "rb").read()).hexdigest() == src["candidates_file_sha256"], "S18 candidates differ from frozen hash"
ids = {r["case_id"] for r in csv.DictReader(open(os.path.join(ROOT, "studies/native_cypherturn_validation/native_cypher/frozen/20261030T083338Z_native_cypher_results/s18_verdicts.csv")))}
rows = {}
for l in open(cand):
    c = json.loads(l)
    if c["case_id"] in ids: rows[c["case_id"]] = {"case_id": c["case_id"], "meta": {"graph": c["graph"]}, "reference": {"query": c["gold_cypher"]}}
assert set(rows) == ids, f"missing {len(ids - set(rows))} frozen S18 IDs among candidates"
with open(out, "w") as f:
    for k in sorted(rows): f.write(json.dumps(rows[k]) + "\n")
print(json.dumps({"s18_cases": len(rows)}))
