#!/usr/bin/env python3
"""study S23 (cross-benchmark replication on Mind the Query) — deterministic candidate generation (s23-rules-v1).
OFFLINE: reads the pinned Mind the Query checkout only (manual test split + db_schema.jsonl); no database, no scorer,
no LLM. Mirrors study S20 (s20-rules-v1) wherever possible; differences are listed below and in the session report.

Source pool (pre-declared): Train_Test_Splits/Manual/<graph>/test/*.json at the pinned commit; a row is ELIGIBLE iff
`logical [0/1]` == "1" (manual correctness label) and `result [0/1]` != "0" where that field exists (ER files have no
result field). Source text normalisation: strip whitespace and one trailing ';' (representation only). Duplicate
(graph, query) texts are kept once.

Classes (each pair targets ONE declared dimension; s23_oracle.py verifies it by execution):
  R1_numeric_type      E2 VALUE_EQUIVALENT_TYPE_DIFFERENT (S20 D1). The first RETURN item that is integer-typed by
                       construction (count(...), or var.prop / sum(var.prop) where db_schema.jsonl declares prop
                       INTEGER for var's label) -> toFloat(item), same column name. Other items unchanged.
  R2_float_tolerance   E3 TOLERANCE_EQUIVALENT (S20 D2). The first item whose expression is exactly AVG(e) ->
                       rule A `toFloat(SUM(e)) / COUNT(e)`; fallback rule B `AVG(e) / 3.0 * 3.0` (tried only if A fails).
  R3_row_order         E5 ORDER_INSENSITIVE_EQUIVALENT (S20 D3). Reference has no ORDER BY / SKIP / LIMIT anywhere ->
                       candidate appends `ORDER BY <every column> DESC`.
  R4_duplicates        E4 SET_EQUIVALENT_MULTISET_DIFFERENT (S20 D4). Reference `RETURN DISTINCT` -> DISTINCT removed.
  R5_column_order      COLUMN_ORDER_POLICY (new; S18 T3 rule, infeasible on CypherTurn). >= 2 RETURN items with
                       distinct column names -> items reversed; names, values and ORDER BY unchanged.
  R6_reference_order   REFERENCE_ORDERED_CANDIDATE_UNORDERED (new; profiling, intent-dependent). Reference has exactly
                       one ORDER BY, in the final RETURN tail, and no SKIP / LIMIT anywhere -> candidate drops it.
  R7_list_order        LIST_ORDER_POLICY (new; profiling, intent-dependent). First item whose expression is exactly
                       collect(...) -> reverse(collect(...)), same column name.
  R8_null_natural      NULL_EQUIVALENT with NATURALLY occurring NULLs (S20 D5 used an appended-column fixture; S23
                       does not synthesise NULLs). Every item e -> coalesce(e, null), same column names; the oracle
                       admits only results that are identical and contain >= 1 NULL and >= 1 non-NULL cell.
                       Sources with OPTIONAL MATCH are ranked first (pre-declared, structure-based, scorer-blind).
  C0_column_name_control COLUMN_NAME_POLICY_CONTROL (S20 D6; calibration only). All items aliased -> alias + '_value',
                       ORDER BY references updated.
Selection (pre-declared, scorer-blind; as S20): per class shuffle the eligible pool with Random(SEED), interleave graphs
round-robin; a source query is used by at most one class; classes are allocated scarcest-first and keep at most
RESERVE candidates. The oracle admits the first QUOTA passing candidates per class in this order.
  python s23_rules.py <mtq_dir> <out_candidates.jsonl>
"""
import glob, hashlib, json, os, random, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from s23_parse import split_query, rebuild, item_alias, column_name, as_item, has_order_skip_limit_anywhere, \
    count_order_by, normalise_source

CLASSES = {
    "R1_numeric_type": "VALUE_EQUIVALENT_TYPE_DIFFERENT",
    "R2_float_tolerance": "TOLERANCE_EQUIVALENT",
    "R3_row_order": "ORDER_INSENSITIVE_EQUIVALENT",
    "R4_duplicates": "SET_EQUIVALENT_MULTISET_DIFFERENT",
    "R5_column_order": "COLUMN_ORDER_POLICY",
    "R6_reference_order": "REFERENCE_ORDERED_CANDIDATE_UNORDERED",
    "R7_list_order": "LIST_ORDER_POLICY",
    "R8_null_natural": "NULL_EQUIVALENT",
    "C0_column_name_control": "COLUMN_NAME_POLICY_CONTROL",
}
QUOTA = {c: 10 for c in CLASSES} | {"C0_column_name_control": 5}
RESERVE = 80
SEED = 23
EPSILON_REL = 1e-9   # R2: 0 < |cand - ref| <= EPSILON_REL * max(1, |ref|)  (unchanged from S20; frozen before execution)
GRAPHS = {  # Manual-split folder -> dump file in Datasets/ (README dataset list)
    "bloom": "bloom-50.dump", "covid": "contact-tracing-50.dump", "er": "entity-resolution-50.dump",
    "healthcare": "healthcare-analytics-50.dump", "wwc": "wwc2019-50.dump",
}
SCHEMA_KEY = {"bloom": "bloom50", "covid": "covid", "er": "er", "healthcare": "healthcare", "wwc": "wwc"}


def load_sources(mtq):
    seen, out, raw = set(), [], 0
    for f in sorted(glob.glob(os.path.join(mtq, "Train_Test_Splits", "Manual", "*", "test", "*.json"))):
        graph = f.split(os.sep)[-3]
        for x in json.load(open(f, encoding="utf-8")):
            raw += 1
            if str(x.get("logical [0/1]")) != "1" or str(x.get("result [0/1]", "1")) == "0": continue
            q = normalise_source(x["Cypher"])
            if (graph, q) in seen: continue
            seen.add((graph, q))
            out.append({"graph": graph, "source_id": x["unique_id"], "source_file": os.path.relpath(f, mtq),
                        "question": x["NL Question"], "gold_cypher_raw": x["Cypher"], "gold_cypher": q})
    return out, raw


def int_props(mtq):
    """graph -> label -> set of INTEGER properties (db_schema.jsonl)."""
    out = {}
    for line in open(os.path.join(mtq, "db_schema.jsonl"), encoding="utf-8"):
        for k, v in json.loads(line).items():
            out[k] = {lab: {p["property"] for p in ps if p.get("datatype") == "INTEGER"}
                      for lab, ps in v.get("node_props", {}).items()}
    return {g: out.get(SCHEMA_KEY[g], {}) for g in GRAPHS}


def var_labels(q):
    return {m.group(1): m.group(2) for m in re.finditer(r"\(\s*([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)", q)}


def is_int_expr(e, q, ints):
    if re.fullmatch(r"count\s*\((.*)\)", e, re.I | re.S): return True
    m = re.fullmatch(r"(?:sum\s*\(\s*)?([A-Za-z_]\w*)\.([A-Za-z_]\w*)(?:\s*\))?", e, re.I)
    if not m or e.count("(") != e.count(")"): return False
    lab = var_labels(q).get(m.group(1))
    return lab is not None and m.group(2) in ints.get(lab, set())


def wrap(p, idx, new_expr):
    e, _ = item_alias(p["items"][idx])
    it = as_item(new_expr, column_name(p["items"][idx]))
    if it is None: return None
    items = list(p["items"]); items[idx] = it
    return rebuild({**p, "items": items})


def r1(g, ints):
    p = split_query(g["gold_cypher"])
    if not p: return []
    for i, it in enumerate(p["items"]):
        e, _ = item_alias(it)
        if is_int_expr(e, g["gold_cypher"], ints.get(g["graph"], {})):
            c = wrap(p, i, f"toFloat({e})")
            return [("R1", c)] if c else []
    return []


AVG_RE = re.compile(r"^AVG\s*\((.*)\)$", re.I | re.S)
COLLECT_RE = re.compile(r"^collect\s*\((.*)\)$", re.I | re.S)


def balanced(x):
    d = 0
    for ch in x:
        d += ch == "("; d -= ch == ")"
        if d < 0: return False
    return d == 0


def r2(g):
    p = split_query(g["gold_cypher"])
    if not p: return []
    for i, it in enumerate(p["items"]):
        e, _ = item_alias(it); m = AVG_RE.match(e)
        if m and balanced(m.group(1)):
            inner = m.group(1)
            a, b = wrap(p, i, f"toFloat(SUM({inner})) / COUNT({inner})"), wrap(p, i, f"AVG({inner}) / 3.0 * 3.0")
            return [x for x in [("R2A", a), ("R2B", b)] if x[1]]
    return []


def r3(g):
    q = g["gold_cypher"]; p = split_query(q)
    if not p or has_order_skip_limit_anywhere(q): return []
    keys = []
    for it in p["items"]:
        e, a = item_alias(it)
        keys.append(a if a else e)
    return [("R3", rebuild({**p, "order_by": ", ".join(f"{k} DESC" for k in keys)}))]


def r4(g):
    p = split_query(g["gold_cypher"])
    if not p or not p["distinct"]: return []
    return [("R4", rebuild({**p, "distinct": False}))]


def r5(g):
    p = split_query(g["gold_cypher"])
    if not p or len(p["items"]) < 2: return []
    names = [column_name(i) for i in p["items"]]
    if len(set(names)) != len(names): return []
    return [("R5", rebuild({**p, "items": list(reversed(p["items"]))}))]


def r6(g):
    q = g["gold_cypher"]; p = split_query(q)
    if not p or not p["order_by"] or p["skip_limit"] or count_order_by(q) != 1: return []
    if re.search(r"\b(SKIP|LIMIT)\b", q, re.I): return []
    return [("R6", rebuild({**p, "order_by": None}))]


def r7(g):
    p = split_query(g["gold_cypher"])
    if not p: return []
    for i, it in enumerate(p["items"]):
        e, _ = item_alias(it)
        if COLLECT_RE.match(e) and balanced(COLLECT_RE.match(e).group(1)):
            c = wrap(p, i, f"reverse({e})")
            return [("R7", c)] if c else []
    return []


def r8(g):
    p = split_query(g["gold_cypher"])
    if not p: return []
    items = []
    for it in p["items"]:
        e, _ = item_alias(it); new = as_item(f"coalesce({e}, null)", column_name(it))
        if new is None: return []
        items.append(new)
    return [("R8", rebuild({**p, "items": items}))]


def c0(g):
    p = split_query(g["gold_cypher"])
    if not p: return []
    pairs = [item_alias(i) for i in p["items"]]
    if any(a is None or a.startswith("`") for _, a in pairs): return []
    mp = {a: a + "_value" for _, a in pairs}
    ob = p["order_by"]
    if ob:
        for a, b in mp.items(): ob = re.sub(r"(?<![\w.`])" + re.escape(a) + r"(?![\w(`])", b, ob)
    return [("C0", rebuild({**p, "items": [f"{e} AS {mp[a]}" for e, a in pairs], "order_by": ob}))]


def variants(cls, g, ints):
    q = g["gold_cypher"]
    fn = {"R1_numeric_type": lambda: r1(g, ints), "R2_float_tolerance": lambda: r2(g), "R3_row_order": lambda: r3(g),
          "R4_duplicates": lambda: r4(g), "R5_column_order": lambda: r5(g), "R6_reference_order": lambda: r6(g),
          "R7_list_order": lambda: r7(g), "R8_null_natural": lambda: r8(g),
          "C0_column_name_control": lambda: c0(g)}[cls]
    return [(r, q, c) for r, c in fn() if c and c != q]


def order_pool(cls, pool):
    pool = list(pool); random.Random(SEED).shuffle(pool)
    if cls == "R8_null_natural":   # pre-declared structural priority: OPTIONAL MATCH sources first (stable)
        pool.sort(key=lambda gv: 0 if re.search(r"\bOPTIONAL\s+MATCH\b", gv[0]["gold_cypher"], re.I) else 1)
    by_graph = {}
    for g, v in pool: by_graph.setdefault(g["graph"], []).append((g, v))
    if cls == "R8_null_natural":
        order = []
        for prio in (0, 1):
            bg = {gr: [x for x in xs if (0 if re.search(r"\bOPTIONAL\s+MATCH\b", x[0]["gold_cypher"], re.I) else 1) == prio]
                  for gr, xs in by_graph.items()}
            while any(bg.values()):
                for gr in sorted(bg):
                    if bg[gr]: order.append(bg[gr].pop(0))
        return order
    order = []
    while any(by_graph.values()):
        for gr in sorted(by_graph):
            if by_graph[gr]: order.append(by_graph[gr].pop(0))
    return order


def build(mtq):
    gold, raw = load_sources(mtq); ints = int_props(mtq)
    pools = {cls: [(g, variants(cls, g, ints)) for g in gold] for cls in CLASSES}
    pools = {cls: [(g, v) for g, v in p if v] for cls, p in pools.items()}
    used, cands = set(), []
    for cls in sorted(CLASSES, key=lambda c: (len(pools[c]), c)):
        rank = 0
        for g, v in order_pool(cls, pools[cls]):
            key = (g["graph"], g["gold_cypher"])
            if key in used: continue
            if rank >= RESERVE: break
            used.add(key); rank += 1
            for sub, (rule, ref_q, cand_q) in enumerate(v):
                cid = "S23-" + hashlib.sha256(f"{cls}|{rule}|{g['graph']}|{g['gold_cypher']}".encode()).hexdigest()[:10]
                cands.append({"case_id": cid, "class": cls, "equivalence_class": CLASSES[cls], "rule": rule,
                              "rank": rank, "sub_rank": sub, "graph": g["graph"], "source_id": g["source_id"],
                              "source_file": g["source_file"], "question": g["question"],
                              "source_gold_cypher_raw": g["gold_cypher_raw"], "source_gold_cypher": g["gold_cypher"],
                              "reference_cypher": ref_q, "candidate_cypher": cand_q,
                              "controlled_fixture": False})
    return gold, raw, pools, cands


def main():
    mtq, out = sys.argv[1:3]
    gold, raw, pools, cands = build(mtq)
    with open(out, "w") as f:
        for c in cands: f.write(json.dumps(c) + "\n")
    from collections import Counter
    print(json.dumps({"manual_test_rows": raw, "eligible_distinct_sources": len(gold),
                      "eligible_per_graph": Counter(g["graph"] for g in gold),
                      "eligible_per_class": {c: len(p) for c, p in pools.items()},
                      "eligible_per_class_graph": {c: Counter(g["graph"] for g, _ in p) for c, p in pools.items()},
                      "candidates_per_class": Counter(c["class"] for c in cands if c["sub_rank"] == 0),
                      "sha256": hashlib.sha256(open(out, "rb").read()).hexdigest()}, indent=1, default=dict))


if __name__ == "__main__":
    main()
