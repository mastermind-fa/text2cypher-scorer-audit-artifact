#!/usr/bin/env python3
"""Policy-sensitive feature exposure in public Text-to-Cypher gold data. Rules frozen in PROTOCOL.md.

Offline and deterministic: reads pinned local benchmark files, no network, no database. Exposure is an upper bound on
opportunities for a policy difference to matter, not a disagreement rate.

  python3 studies/exposure_and_released_path/exposure/exposure.py [--root <artifact root>] [--out <dir>]
"""
import argparse
import csv
import glob
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))

QUERY_FEATURES = ["Q_ORDER_TRIGGER", "Q_FINAL_ORDER_BY", "Q_ORDER_BY_NO_LIMIT", "Q_LIMIT", "Q_RETURN_DISTINCT",
                  "Q_AGGREGATE", "Q_FLOAT_EXPR", "Q_MULTI_ITEM", "Q_UNALIASED_ITEM", "Q_COLLECTION_EXPR",
                  "Q_OPTIONAL_MATCH", "Q_UNION", "Q_GRAPH_VALUE_ITEM", "Q_UNPARSED"]
# features computed from the parsed final RETURN; undetermined (None) when the query does not parse
PARSED_ONLY = {"Q_FINAL_ORDER_BY", "Q_ORDER_BY_NO_LIMIT", "Q_LIMIT", "Q_RETURN_DISTINCT", "Q_AGGREGATE", "Q_FLOAT_EXPR",
               "Q_MULTI_ITEM", "Q_UNALIASED_ITEM", "Q_COLLECTION_EXPR", "Q_GRAPH_VALUE_ITEM"}
RESULT_FEATURES = ["R_EMPTY", "R_MULTI_ROW", "R_MULTI_COL", "R_NULL", "R_NUMERIC_NULL_COL", "R_NUMERIC", "R_FLOAT",
                   "R_NONINTEGRAL_FLOAT", "R_INT_FLOAT_MIXED_COL", "R_DUPLICATE_ROWS", "R_LIST", "R_MAP"]
DIMENSION = {
    "Q_ORDER_TRIGGER": "row order; query-text dependence", "Q_FINAL_ORDER_BY": "row order",
    "Q_ORDER_BY_NO_LIMIT": "row order", "Q_LIMIT": "row order (top-k ties)", "Q_RETURN_DISTINCT": "duplicates",
    "Q_AGGREGATE": "numeric type", "Q_FLOAT_EXPR": "numeric tolerance", "Q_MULTI_ITEM": "column names; column position",
    "Q_UNALIASED_ITEM": "column names", "Q_COLLECTION_EXPR": "collections", "Q_OPTIONAL_MATCH": "NULLs",
    "Q_UNION": "query-text dependence", "Q_GRAPH_VALUE_ITEM": "graph-valued results", "Q_UNPARSED": "parser coverage",
    "R_EMPTY": "empty results", "R_MULTI_ROW": "row order", "R_MULTI_COL": "column names; column position",
    "R_NULL": "NULLs", "R_NUMERIC_NULL_COL": "NULLs (GQLBench NaN)", "R_NUMERIC": "numeric type",
    "R_FLOAT": "numeric type", "R_NONINTEGRAL_FLOAT": "numeric tolerance", "R_INT_FLOAT_MIXED_COL": "numeric type",
    "R_DUPLICATE_ROWS": "duplicates", "R_LIST": "collections", "R_MAP": "collections / graph objects",
}

AGG = r"\b(count|sum|avg|min|max|stdev|stdevp|percentilecont|percentiledisc)\s*\("
FLOATFN = r"\b(avg|stdev|stdevp|percentilecont|percentiledisc|tofloat|round)\s*\("
COLLFN = r"\b(collect|keys|labels|nodes|relationships|range|split|tail|reverse)\s*\("
IDENT = r"[A-Za-z_][A-Za-z0-9_]*"


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


PARSER_DIRS = ["studies/native_mind_the_query/mind_the_query_replication/code"]


def parser_path(root):
    return next(os.path.join(root, d) for d in PARSER_DIRS if os.path.exists(os.path.join(root, d, "s23_parse.py")))


def load_parser(root):
    sys.path.insert(0, parser_path(root))
    import s23_parse
    return s23_parse


def query_features(q, P):
    masked, _, _ = P._mask(q)
    f = {"Q_ORDER_TRIGGER": "order by" in q.lower(),
         "Q_OPTIONAL_MATCH": bool(re.search(r"\bOPTIONAL\s+MATCH\b", masked, re.I)),
         "Q_UNION": bool(re.search(r"\bUNION\b", masked, re.I))}
    p = P.split_query(q)
    f["Q_UNPARSED"] = p is None
    if p is None:
        f.update({k: None for k in PARSED_ONLY})
        return f
    items = p["items"]
    m_items = [P._mask(it)[0] for it in items]
    tail = " ".join(p["skip_limit"])
    f["Q_FINAL_ORDER_BY"] = p["order_by"] is not None
    f["Q_LIMIT"] = bool(re.search(r"\bLIMIT\b", tail, re.I))
    f["Q_ORDER_BY_NO_LIMIT"] = f["Q_FINAL_ORDER_BY"] and not f["Q_LIMIT"]
    f["Q_RETURN_DISTINCT"] = p["distinct"]
    f["Q_AGGREGATE"] = any(re.search(AGG, m, re.I) for m in m_items)
    f["Q_FLOAT_EXPR"] = any(re.search(FLOATFN, m, re.I) or "/" in m for m in m_items)
    f["Q_MULTI_ITEM"] = len(items) >= 2
    f["Q_UNALIASED_ITEM"] = any(P.item_alias(it)[1] is None for it in items)
    f["Q_COLLECTION_EXPR"] = any("[" in m or "{" in m or re.search(COLLFN, m, re.I) for m in m_items)
    head = P._mask(p["head"])[0]
    graph_vars = set(re.findall(r"\(\s*(" + IDENT + r")\s*[:){]", head))
    graph_vars |= set(re.findall(r"\[\s*(" + IDENT + r")\s*[:\]{*]", head))
    graph_vars |= set(re.findall(r"\b(" + IDENT + r")\s*=\s*(?:shortestPath|allShortestPaths|\()", head, re.I))
    f["Q_GRAPH_VALUE_ITEM"] = any(P.item_alias(it)[0] in graph_vars for it in items)
    return f


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def result_features(rows):
    """rows: list of dicts (column order = key order). Returns (features, key_mismatch)."""
    if not rows:
        f = {k: False for k in RESULT_FEATURES}
        f["R_EMPTY"] = True
        return f, False
    cols = list(rows[0].keys())
    mismatch = any(list(r.keys()) != cols for r in rows)
    cells = [v for r in rows for v in r.values()]
    by_col = {c: [r.get(c) for r in rows] for c in cols}
    canon = Counter(json.dumps([r.get(c) for c in cols], sort_keys=True) for r in rows)
    f = {
        "R_EMPTY": False,
        "R_MULTI_ROW": len(rows) >= 2,
        "R_MULTI_COL": len(cols) >= 2,
        "R_NULL": any(v is None for v in cells),
        "R_NUMERIC_NULL_COL": any(any(v is None for v in vs) and any(v is not None for v in vs)
                                  and all(is_num(v) for v in vs if v is not None) for vs in by_col.values()),
        "R_NUMERIC": any(is_num(v) for v in cells),
        "R_FLOAT": any(isinstance(v, float) for v in cells),
        "R_NONINTEGRAL_FLOAT": any(isinstance(v, float) and math.isfinite(v) and v != int(v) for v in cells),
        "R_INT_FLOAT_MIXED_COL": any(any(isinstance(v, float) for v in vs) and
                                     any(isinstance(v, int) and not isinstance(v, bool) for v in vs)
                                     for vs in by_col.values()),
        "R_DUPLICATE_ROWS": any(n >= 2 for n in canon.values()),
        "R_LIST": any(isinstance(v, list) for v in cells),
        "R_MAP": any(isinstance(v, dict) for v in cells),
    }
    return f, mismatch


def load_cypherturn(root):
    files = sorted(glob.glob(os.path.join(root, "external/cypherturn/data/scenarios/*_sessions.json")))
    items = []
    for p in files:
        for s in json.load(open(p)):
            for t in s["turns"]:
                q = (t.get("gold_cypher") or "").strip()
                if not q:
                    continue
                ans = t.get("gold_answer")
                items.append({"benchmark": "CypherTurn", "graph": s["graph"], "split": s.get("split"),
                              "item_id": f"{s['session_id']}:{t['turn_id']}", "query": q,
                              "rows": ans if isinstance(ans, list) else None})
    return files, items


def load_mtq(root, results_path=None):
    """Gold rows exist only if the approval-bound mtq_results/run_mtq_gold.sh has been run; otherwise rows = None."""
    files = sorted(glob.glob(os.path.join(root, "external/mind_the_query/Train_Test_Splits/Manual/*/test/*.json")))
    executed = {}
    if results_path and os.path.exists(results_path):
        for line in open(results_path):
            r = json.loads(line)
            executed[(r["graph"], r["item_id"], r["query"])] = r.get("rows") if "error" not in r else None
    items = []
    for p in files:
        graph = p.split(os.sep)[-3]
        for r in json.load(open(p)):
            q = (r.get("Cypher") or "").strip()
            if not q:
                continue
            items.append({"benchmark": "Mind the Query", "graph": graph, "split": "test",
                          "item_id": r["unique_id"], "query": q, "logical": str(r.get("logical [0/1]")).strip() == "1",
                          "rows": executed.get((graph, r["unique_id"], q))})
    if executed:
        files = files + [results_path]
    return files, items


def tally(items, P, population):
    n = len(items)
    q_counts, q_det = Counter(), Counter()
    r_counts, n_res, mism = Counter(), 0, 0
    for it in items:
        f = query_features(it["query"], P)
        for k, v in f.items():
            if v is not None:
                q_det[k] += 1
                q_counts[k] += int(v)
        if it["rows"] is not None:
            n_res += 1
            rf, mm = result_features(it["rows"])
            mism += int(mm)
            for k, v in rf.items():
                r_counts[k] += int(v)
    out = []
    for k in QUERY_FEATURES:
        out.append({"population": population, "level": "query", "feature": k, "dimension": DIMENSION[k],
                    "count": q_counts[k], "denominator": q_det[k], "items": n,
                    "pct": round(100 * q_counts[k] / q_det[k], 1) if q_det[k] else None})
    for k in RESULT_FEATURES:
        out.append({"population": population, "level": "result", "feature": k, "dimension": DIMENSION[k],
                    "count": r_counts[k] if n_res else None, "denominator": n_res, "items": n,
                    "pct": round(100 * r_counts[k] / n_res, 1) if n_res else None})
    return out, {"population": population, "items": n, "results_available": n_res, "key_order_mismatch": mism}


def distinct(items):
    seen, out = set(), []
    for it in items:
        key = (it["graph"], it["query"])
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.abspath(os.path.join(HERE, "../../..")))
    ap.add_argument("--out", default=os.path.join(HERE, "outputs"))
    a = ap.parse_args()
    P = load_parser(a.root)
    ct_files, ct = load_cypherturn(a.root)
    mq_files, mq = load_mtq(a.root, os.path.join(HERE, "mtq_results/mtq_gold_results.jsonl"))
    pops = [("CypherTurn: all turns", ct)]
    for sp in sorted({i["split"] for i in ct}, key=str):
        pops.append((f"CypherTurn: split={sp}", [i for i in ct if i["split"] == sp]))
    pops += [("CypherTurn: distinct (graph, query)", distinct(ct)),
             ("Mind the Query: all test rows", mq),
             ("Mind the Query: logical=1", [i for i in mq if i["logical"]]),
             ("Mind the Query: logical=1, distinct (graph, query)", distinct([i for i in mq if i["logical"]]))]
    rows, denoms = [], []
    for name, items in pops:
        r, d = tally(items, P, name)
        rows += r
        denoms.append(d)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "exposure_counts.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    code = [os.path.join(HERE, "exposure.py"),
            os.path.join(parser_path(a.root), "s23_parse.py")]
    manifest = {"inputs": {os.path.relpath(p, a.root): sha_file(p) for p in ct_files + mq_files},
                "code": {os.path.relpath(p, a.root): sha_file(p) for p in code},
                "protocol": {os.path.relpath(os.path.join(HERE, "PROTOCOL.md"), a.root): sha_file(os.path.join(HERE, "PROTOCOL.md"))}}
    json.dump(manifest, open(os.path.join(a.out, "input_manifest.json"), "w"), indent=1, sort_keys=True)
    json.dump({"denominators": denoms, "counts": rows}, open(os.path.join(a.out, "exposure_counts.json"), "w"), indent=1)
    # Markdown summary: primary populations side by side
    prim = {"CypherTurn: all turns": "CypherTurn", "Mind the Query: all test rows": "Mind the Query"}
    idx = {(r["population"], r["feature"]): r for r in rows}
    lines = ["# Policy-sensitive feature exposure (upper bound on opportunities, not disagreement)", "",
             "| Population | items | results available | key-order mismatches |", "|---|---|---|---|"]
    lines += [f"| {d['population']} | {d['items']} | {d['results_available']} | {d['key_order_mismatch']} |" for d in denoms]
    lines += ["", "| Feature | Dimension | " + " | ".join(prim.values()) + " |", "|---|---|" + "---|" * len(prim)]
    for k in QUERY_FEATURES + RESULT_FEATURES:
        cells = []
        for p in prim:
            r = idx[(p, k)]
            cells.append("not available" if r["count"] is None else f"{r['count']}/{r['denominator']} ({r['pct']}%)")
        lines.append(f"| {k} | {DIMENSION[k]} | " + " | ".join(cells) + " |")
    open(os.path.join(a.out, "exposure_summary.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
