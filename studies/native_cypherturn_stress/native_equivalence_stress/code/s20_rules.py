#!/usr/bin/env python3
"""study S20 (post-freeze native-Cypher result-equivalence stress test) — deterministic candidate generation
(s20-rules-v1). OFFLINE: reads CypherTurn's released files only; no database, no scorer, no LLM.

Source: CypherTurn released gold Cypher + released gold answers (BarryQ/CypherTurn @ pinned commit,
data/scenarios/*_sessions.json) and graph files (data/graphs/*/data.cypher).

Classes (each pair targets exactly ONE declared equivalence dimension; the oracle in s20_oracle.py verifies it):
  D1_numeric_type   E2 VALUE_EQUIVALENT_TYPE_DIFFERENT   final single RETURN item `e AS a` -> `toFloat(e) AS a`;
                    eligible if every released gold-answer value is an integer (not bool)
  D2_float_tolerance E3 TOLERANCE_EQUIVALENT             `AVG(e) AS a` -> rule A `toFloat(SUM(e)) / COUNT(e) AS a`
                    (mathematically identical aggregate form); fallback rule B `AVG(e) / 3.0 * 3.0 AS a` (identical in
                    exact arithmetic) — B is tried for a source only if A fails the oracle (pre-declared)
  D3_row_order      E5 ORDER_INSENSITIVE_EQUIVALENT      reference without any ORDER BY / SKIP / LIMIT, >= 2 released rows
                    -> append `ORDER BY a DESC` to the candidate
  D4_duplicates     E4 SET_EQUIVALENT_MULTISET_DIFFERENT reference `RETURN DISTINCT ...` -> candidate without DISTINCT
  D5_null_controlled E6 NULL_EQUIVALENT (CONTROLLED FIXTURE, reported separately): reference = gold query with one
                    appended item `v.P AS p_opt`, where v is bound to a label on which property P is missing for some
                    nodes in the released graph and P is not mentioned anywhere in the gold query; candidate = same with `coalesce(v.P, null) AS p_opt`
  D6_column_name_control COLUMN_NAME_POLICY_CONTROL (calibration only, not new evidence): study S18 T1 alias rename
Selection (pre-declared, scorer-blind): dedupe gold texts; exclude every (graph, query) admitted in study S18; per class
shuffle the eligible pool with Random(SEED) and interleave graphs round-robin; a source query is used by at most one
class; classes are allocated scarcest-first and keep at most RESERVE candidates. The oracle admits the first QUOTA
passing candidates per class in this order.
  python s20_rules.py <cypherturn_dir> <s18_cases.jsonl> <out_candidates.jsonl>
"""
import glob, hashlib, json, os, random, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "native_cypherturn_validation", "native_cypher", "code"))
from s18_rewrite import parse_return, item_alias, rebuild, sub_tail, t1  # frozen S18 parser (reused unchanged)

CLASSES = {
    "D1_numeric_type": "VALUE_EQUIVALENT_TYPE_DIFFERENT",
    "D2_float_tolerance": "TOLERANCE_EQUIVALENT",
    "D3_row_order": "ORDER_INSENSITIVE_EQUIVALENT",
    "D4_duplicates": "SET_EQUIVALENT_MULTISET_DIFFERENT",
    "D5_null_controlled": "NULL_EQUIVALENT",
    "D6_column_name_control": "COLUMN_NAME_POLICY_CONTROL",
}
QUOTA = {"D1_numeric_type": 15, "D2_float_tolerance": 15, "D3_row_order": 15, "D4_duplicates": 15,
         "D5_null_controlled": 10, "D6_column_name_control": 5}
RESERVE = 40
SEED = 20
EPSILON_REL = 1e-9   # D2: 0 < |cand - ref| <= EPSILON_REL * max(1, |ref|)  (frozen before any execution)


def single_item(q):
    p = parse_return(q)
    if not p or len(p[2]) != 1: return None
    head, d, items, tail = p
    e, a = item_alias(items[0])
    if a is None: return None
    return head, d, e, a, tail


def answer_values(ans):
    if not isinstance(ans, list): return None
    vals = []
    for r in ans:
        if not isinstance(r, dict) or len(r) != 1: return None
        vals.extend(r.values())
    return vals


def d1(g):
    s = single_item(g["gold_cypher"]); vals = answer_values(g["gold_answer"])
    if not s or not vals or not all(isinstance(v, int) and not isinstance(v, bool) for v in vals): return []
    head, d, e, a, tail = s
    return [("D1", rebuild(head, d, [f"toFloat({e}) AS {a}"], tail))]


AVG_RE = re.compile(r"^AVG\((.*)\)$", re.I | re.S)


def balanced(x):
    depth = 0
    for ch in x:
        depth += ch == "("; depth -= ch == ")"
        if depth < 0: return False
    return depth == 0


def d2(g):
    s = single_item(g["gold_cypher"])
    if not s: return []
    head, d, e, a, tail = s
    m = AVG_RE.match(e)
    if not m or not balanced(m.group(1)): return []
    inner = m.group(1)
    return [("D2A", rebuild(head, d, [f"toFloat(SUM({inner})) / COUNT({inner}) AS {a}"], tail)),
            ("D2B", rebuild(head, d, [f"AVG({inner}) / 3.0 * 3.0 AS {a}"], tail))]


def d3(g):
    q = g["gold_cypher"]; s = single_item(q); vals = answer_values(g["gold_answer"])
    if not s or not vals or len(vals) < 2: return []
    if re.search(r"\b(ORDER\s+BY|SKIP|LIMIT)\b", q, re.I): return []
    head, d, e, a, tail = s
    return [("D3", rebuild(head, d, [f"{e} AS {a}"], tail + [f"ORDER BY {a} DESC"]))]


def d4(g):
    s = single_item(g["gold_cypher"])
    if not s or not s[1]: return []
    head, _, e, a, tail = s
    return [("D4", rebuild(head, False, [f"{e} AS {a}"], tail))]


def label_props(ct_dir):
    """graph -> label -> sorted properties that are missing on some nodes of that label (released data.cypher)."""
    out = {}
    for f in sorted(glob.glob(os.path.join(ct_dir, "data", "graphs", "*", "data.cypher"))):
        graph = os.path.basename(os.path.dirname(f)); txt = open(f, encoding="utf-8").read()
        props, cnt = {}, {}
        for m in re.finditer(r"\((\w*):(\w+)\s*\{([^}]*)\}\)", txt):
            lab = m.group(2); cnt[lab] = cnt.get(lab, 0) + 1
            for k in re.findall(r"(\w+)\s*:", m.group(3)): props.setdefault(lab, {}).setdefault(k, 0); props[lab][k] += 1
        out[graph] = {lab: sorted(k for k, c in ks.items() if c < cnt[lab]) for lab, ks in props.items()}
    return out


def d5(g, hetero):
    s = single_item(g["gold_cypher"])
    if not s: return []
    head, d, e, a, tail = s
    m = re.fullmatch(r"([A-Za-z_]\w*)\.([A-Za-z_]\w*)", e)
    if not m: return []
    var, prop = m.groups()
    lm = re.search(r"\(" + re.escape(var) + r":(\w+)", g["gold_cypher"])
    if not lm: return []
    cand_props = [p for p in hetero.get(g["graph"], {}).get(lm.group(1), [])
                  if p != prop and not re.search(r"\b" + re.escape(p) + r"\b", g["gold_cypher"])]
    if not cand_props: return []
    P = cand_props[0]
    ref = rebuild(head, d, [f"{e} AS {a}", f"{var}.{P} AS p_opt"], tail)
    cand = rebuild(head, d, [f"{e} AS {a}", f"coalesce({var}.{P}, null) AS p_opt"], tail)
    return [("D5", ref, cand)]


def d6(g):
    rw = t1(g["gold_cypher"])
    return [("D6", rw)] if rw and single_item(g["gold_cypher"]) else []


def load_gold(ct_dir):
    seen, out = set(), []
    for f in sorted(glob.glob(os.path.join(ct_dir, "data", "scenarios", "*_sessions.json"))):
        graph = os.path.basename(f).replace("_sessions.json", "")
        for s in json.load(open(f)):
            for t in s["turns"]:
                q = (t.get("gold_cypher") or "").strip()
                if not q or (graph, q) in seen: continue
                seen.add((graph, q))
                out.append({"graph": graph, "session_id": s["session_id"], "turn_id": t["turn_id"], "gold_cypher": q,
                            "gold_answer": t.get("gold_answer")})
    return out


def variants(cls, g, hetero):
    """-> list of (rule, reference_query, candidate_query)."""
    q = g["gold_cypher"]
    if cls == "D1_numeric_type": return [(r, q, c) for r, c in d1(g)]
    if cls == "D2_float_tolerance": return [(r, q, c) for r, c in d2(g)]
    if cls == "D3_row_order": return [(r, q, c) for r, c in d3(g)]
    if cls == "D4_duplicates": return [(r, q, c) for r, c in d4(g)]
    if cls == "D5_null_controlled": return d5(g, hetero)
    if cls == "D6_column_name_control": return [(r, q, c) for r, c in d6(g)]
    raise ValueError(cls)


def build(ct_dir, s18_cases):
    gold = load_gold(ct_dir); hetero = label_props(ct_dir)
    s18_used = set()
    for l in open(s18_cases):
        c = json.loads(l); s18_used.add((c["meta"]["graph"], c["reference"]["query"]))
    gold = [g for g in gold if (g["graph"], g["gold_cypher"]) not in s18_used]
    pools = {cls: [(g, variants(cls, g, hetero)) for g in gold] for cls in CLASSES}
    pools = {cls: [(g, v) for g, v in p if v and all(c != r for _, r, c in v)] for cls, p in pools.items()}
    used, cands = set(), []
    for cls in sorted(CLASSES, key=lambda c: (len(pools[c]), c)):
        pool = list(pools[cls]); random.Random(SEED).shuffle(pool)
        by_graph = {}
        for g, v in pool: by_graph.setdefault(g["graph"], []).append((g, v))
        order, graphs = [], sorted(by_graph)
        while any(by_graph.values()):
            for gr in graphs:
                if by_graph[gr]: order.append(by_graph[gr].pop(0))
        rank = 0
        for g, v in order:
            key = (g["graph"], g["gold_cypher"])
            if key in used: continue
            if rank >= RESERVE: break
            used.add(key); rank += 1
            for sub, (rule, ref_q, cand_q) in enumerate(v):
                cid = "S20-" + hashlib.sha256(f"{cls}|{rule}|{g['graph']}|{g['gold_cypher']}".encode()).hexdigest()[:10]
                cands.append({"case_id": cid, "class": cls, "equivalence_class": CLASSES[cls], "rule": rule,
                              "rank": rank, "sub_rank": sub, "graph": g["graph"], "session_id": g["session_id"],
                              "turn_id": g["turn_id"], "source_gold_cypher": g["gold_cypher"],
                              "reference_cypher": ref_q, "candidate_cypher": cand_q,
                              "controlled_fixture": cls == "D5_null_controlled"})
    return gold, pools, cands


def main():
    ct_dir, s18_cases, out = sys.argv[1:4]
    gold, pools, cands = build(ct_dir, s18_cases)
    with open(out, "w") as f:
        for c in cands: f.write(json.dumps(c) + "\n")
    from collections import Counter
    print(json.dumps({"distinct_gold_after_s18_exclusion": len(gold),
                      "eligible_per_class": {c: len(p) for c, p in pools.items()},
                      "candidates_per_class": Counter(c["class"] for c in cands if c["sub_rank"] == 0),
                      "sha256": hashlib.sha256(open(out, "rb").read()).hexdigest()}, indent=1, default=dict))


if __name__ == "__main__":
    main()
