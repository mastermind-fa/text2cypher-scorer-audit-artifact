#!/usr/bin/env python3
"""Build the MAIN_AUDIT S3 (primary) and S2 (secondary) result-pair files from frozen sources (audit-pairs-v1).

Protocol audit-protocol-v1 §P6 — no exclusions; flags only. Output pairs use the MAIN_AUDIT representation consumed by the
frozen adapters: {"case_id", "reference": {"query","columns","rows"}, "prediction": {"query","columns","rows"},
"meta": {...}}. Columns come from the first row's key order (as a driver returns them); rows are value lists in that
order. Empty results have columns [] (the stored outputs carry no column names when empty).

  python build_pairs.py <outdir>
"""
import hashlib
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
DATASET = os.path.join(ROOT, "database", "dataset.json")
EXEC = os.path.join(ROOT, "withheld", "pilot_predictions", "attempt2", "execution", "primary_execution_s8c.jsonl")
UNITS = os.path.join(ROOT, "studies", "reference_comparator", "c3_final", "run", "c3_units.jsonl")
DATASET_SHA_PREFIX = "e96196c9b90181d6"


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def side_from_dicts(query, rows):
    """List of dicts -> {query, columns, rows}. Raises if rows have inconsistent key sets (never silently fixed)."""
    if not rows:
        return {"query": query, "columns": [], "rows": []}
    cols = list(rows[0].keys())
    for r in rows:
        if list(r.keys()) != cols:
            raise ValueError(f"inconsistent keys in stored rows for query: {query[:60]}")
    return {"query": query, "columns": cols, "rows": [[r[c] for c in cols] for r in rows]}


def build_s3(dataset):
    pairs = []
    for i, rec in enumerate(dataset):
        so, no = rec.get("sql_output"), rec.get("neo4j_output")
        if not (isinstance(so, list) and isinstance(no, list)):
            continue
        pairs.append({
            "case_id": f"S3-{i:03d}",
            "reference": side_from_dicts(rec["cypher"], no),
            "prediction": side_from_dicts(rec["SQL"], so),
            "meta": {"dataset_index": i, "cluster": rec["question"], "empty_reference": not no,
                     "empty_prediction": not so},
        })
    return pairs


def build_s2(dataset, exec_rows, units):
    idx = {(u["model_key"], u["canonical_id"]): u["dataset_index"] for u in units}
    pairs, not_scored = [], []
    for r in exec_rows:
        if r["graph_variant"] != "G0":
            continue
        uid = f"{r['model_key']}|{r['canonical_id']}"
        if r["execution_status"] != "OK":
            not_scored.append({"unit_id": uid, "execution_status": r["execution_status"]})
            continue
        di = idx[(r["model_key"], r["canonical_id"])]
        gold = dataset[di]
        pred_rows = [dict(zip(r["keys"], row)) for row in (r["rows"] or [])]
        pairs.append({
            "case_id": f"S2-{uid}",
            "reference": side_from_dicts(gold["cypher"], gold["neo4j_output"]),
            "prediction": {"query": r["extracted_cypher"], "columns": list(r["keys"] or []),
                           "rows": [list(row) for row in (r["rows"] or [])]},
            "meta": {"dataset_index": di, "cluster": r["canonical_id"], "model": r["model_key"],
                     "empty_reference": not gold["neo4j_output"], "empty_prediction": not r["rows"],
                     "identical_query_text": r["extracted_cypher"] == gold["cypher"]},
        })
        assert pred_rows is not None
    return pairs, not_scored


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    if not sha(DATASET).startswith(DATASET_SHA_PREFIX):
        raise SystemExit("dataset.json hash mismatch")
    dataset = json.load(open(DATASET))
    s3 = build_s3(dataset)
    s2, not_scored = build_s2(dataset, [json.loads(l) for l in open(EXEC)], [json.loads(l) for l in open(UNITS)])
    files = {}
    for name, data in [("s3_pairs.jsonl", s3), ("s2_pairs.jsonl", s2)]:
        p = os.path.join(out, name)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            for x in data:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        files[name] = sha(p)
    manifest = {
        "pairs_version": "audit-pairs-v1",
        "sources": {"dataset.json": sha(DATASET), "primary_execution_s8c.jsonl": sha(EXEC), "c3_units.jsonl": sha(UNITS)},
        "s3": {"n": len(s3), "empty_reference": sum(p["meta"]["empty_reference"] for p in s3),
               "empty_prediction": sum(p["meta"]["empty_prediction"] for p in s3),
               "distinct_clusters": len({p["meta"]["cluster"] for p in s3})},
        "s2": {"n": len(s2), "empty_prediction": sum(p["meta"]["empty_prediction"] for p in s2),
               "empty_reference": sum(p["meta"]["empty_reference"] for p in s2),
               "identical_query_text": sum(p["meta"]["identical_query_text"] for p in s2),
               "distinct_clusters": len({p["meta"]["cluster"] for p in s2}),
               "models": {m: sum(p["meta"]["model"] == m for p in s2) for m in sorted({p["meta"]["model"] for p in s2})},
               "not_scored_non_ok": len(not_scored)},
        "files_sha256": files,
    }
    json.dump(not_scored, open(os.path.join(out, "s2_not_scored_units.json"), "w"), indent=1)
    json.dump(manifest, open(os.path.join(out, "PAIRS_MANIFEST.json"), "w"), indent=2)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
