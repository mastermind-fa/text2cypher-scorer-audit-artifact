#!/usr/bin/env python3
"""study S18 (post-freeze native-Cypher validation) — deterministic candidate generation (s18-rewrite-v1). OFFLINE.

Source: CypherTurn released gold Cypher (BarryQ/CypherTurn @ pinned commit, data/scenarios/*_sessions.json).
Families (meaning-preserving, rule-based; NO LLM):
  T1 alias rename      every `expr AS a` in the final RETURN -> `expr AS a_value`; trailing ORDER BY refs updated
  T2 drop alias        final RETURN made only of simple `var.prop AS a` items -> `var.prop` (Cypher names the column
                       'var.prop'); trailing ORDER BY refs rewritten to the expression
  T3 column reorder    final RETURN with >= 2 items -> items reversed
  T4 add DISTINCT      final RETURN without DISTINCT -> RETURN DISTINCT (admitted only if the oracle shows the
                       reference result has no duplicate rows)
  T5 numeric literal   first integer literal compared in a WHERE predicate (`<op> 123`) -> `<op> 123.0`
Selection (pre-declared): dedupe gold texts; per family shuffle the eligible pool with Random(42) and interleave graphs
round-robin; a source query is used by at most one family; families are allocated scarcest-first (fewest eligible
queries) and each keeps at most RESERVE = 40 candidates. The oracle then admits the first QUOTA passing candidates
per family in this order; everything else is logged.
  python s18_rewrite.py <cypherturn_dir> <out_candidates.jsonl>
"""
import glob, hashlib, json, os, random, re, sys

FAMILIES = ["T1_alias_rename", "T2_drop_alias", "T3_column_reorder", "T4_add_distinct", "T5_numeric_literal"]
QUOTA = 15            # accepted cases per family (pre-declared before any execution; T3 infeasible on CypherTurn)
RESERVE = 40          # candidates kept per family (quota + reserve for oracle rejections)
SEED = 42

def split_top(s):
    out, depth, cur, q = [], 0, [], None
    for ch in s:
        if q:
            cur.append(ch); q = None if ch == q else q; continue
        if ch in "'\"": q = ch
        elif ch in "([{": depth += 1
        elif ch in ")]}": depth -= 1
        if ch == "," and depth == 0: out.append("".join(cur).strip()); cur = []
        else: cur.append(ch)
    if "".join(cur).strip(): out.append("".join(cur).strip())
    return out

def parse_return(q):
    """-> (head, distinct, items, tail) for a query whose last clause starts with a line 'RETURN ...'; else None.
    tail = following lines (ORDER BY / SKIP / LIMIT)."""
    lines = q.split("\n")
    idx = [i for i, l in enumerate(lines) if l.strip().upper().startswith("RETURN ")]
    if len(idx) != 1 or re.search(r"\bUNION\b", q, re.I) or len(re.findall(r"\bRETURN\b", q, re.I)) != 1: return None
    i = idx[0]
    tail = lines[i + 1:]
    if any(not re.match(r"\s*(ORDER BY|SKIP|LIMIT)\b", t, re.I) for t in tail if t.strip()): return None
    body = lines[i].strip()[len("RETURN "):]
    distinct = body.upper().startswith("DISTINCT ")
    if distinct: body = body[len("DISTINCT "):]
    items = split_top(body)
    return "\n".join(lines[:i]), distinct, items, tail

def item_alias(it):
    m = re.match(r"^(.*?)\s+AS\s+([A-Za-z_][A-Za-z0-9_]*)$", it, re.S)
    return (m.group(1).strip(), m.group(2)) if m else (it.strip(), None)

def rebuild(head, distinct, items, tail):
    ret = "RETURN " + ("DISTINCT " if distinct else "") + ", ".join(items)
    return "\n".join(([head] if head else []) + [ret] + tail)

def sub_tail(tail, mapping):
    out = []
    for t in tail:
        for a, b in mapping.items():
            t = re.sub(r"(?<![\w.])" + re.escape(a) + r"(?![\w(])", b, t)
        out.append(t)
    return out

def t1(q):
    p = parse_return(q)
    if not p: return None
    head, d, items, tail = p
    pairs = [item_alias(i) for i in items]
    if any(a is None for _, a in pairs): return None
    mapping = {a: a + "_value" for _, a in pairs}
    return rebuild(head, d, [f"{e} AS {mapping[a]}" for e, a in pairs], sub_tail(tail, mapping))

def t2(q):
    p = parse_return(q)
    if not p: return None
    head, d, items, tail = p
    pairs = [item_alias(i) for i in items]
    if any(a is None or not re.fullmatch(r"[A-Za-z_]\w*\.[A-Za-z_]\w*", e) for e, a in pairs): return None
    if len({e for e, _ in pairs}) != len(pairs): return None
    return rebuild(head, d, [e for e, _ in pairs], sub_tail(tail, {a: e for e, a in pairs}))

def t3(q):
    p = parse_return(q)
    if not p or len(p[2]) < 2: return None
    head, d, items, tail = p
    return rebuild(head, d, list(reversed(items)), tail)

def t4(q):
    p = parse_return(q)
    if not p or p[1]: return None
    head, _, items, tail = p
    return rebuild(head, True, items, tail)

def t5(q):
    m = None
    for ln_i, ln in enumerate(q.split("\n")):
        if ln.strip().upper().startswith("WHERE"):
            m = re.search(r"(>=|<=|<>|=|<|>)\s*(-?\d+)(?![\d.\w])", ln)
            if m: break
    if not m: return None
    lines = q.split("\n"); ln = lines[ln_i]
    lines[ln_i] = ln[:m.start(2)] + m.group(2) + ".0" + ln[m.end(2):]
    return "\n".join(lines)

RULES = {"T1_alias_rename": t1, "T2_drop_alias": t2, "T3_column_reorder": t3, "T4_add_distinct": t4,
         "T5_numeric_literal": t5}

def load_gold(ct_dir):
    seen, out = set(), []
    for f in sorted(glob.glob(os.path.join(ct_dir, "data", "scenarios", "*_sessions.json"))):
        graph = os.path.basename(f).replace("_sessions.json", "")
        for s in json.load(open(f)):
            for t in s["turns"]:
                q = (t.get("gold_cypher") or "").strip()
                if not q or (graph, q) in seen: continue
                seen.add((graph, q))
                out.append({"graph": graph, "session_id": s["session_id"], "turn_id": t["turn_id"], "gold_cypher": q})
    return out

def build(ct_dir):
    gold = load_gold(ct_dir)
    used, cands = set(), []
    pools = {}
    for fam in FAMILIES:
        pools[fam] = [(g, RULES[fam](g["gold_cypher"])) for g in gold]
        pools[fam] = [(g, rw) for g, rw in pools[fam] if rw and rw != g["gold_cypher"]]
    for fam in sorted(FAMILIES, key=lambda f: (len(pools[f]), f)):
        pool = list(pools[fam])
        rng = random.Random(SEED); rng.shuffle(pool)
        by_graph = {}
        for g, rw in pool: by_graph.setdefault(g["graph"], []).append((g, rw))
        order, graphs = [], sorted(by_graph)
        while any(by_graph.values()):
            for gr in graphs:
                if by_graph[gr]: order.append(by_graph[gr].pop(0))
        rank = 0
        for g, rw in order:
            key = (g["graph"], g["gold_cypher"])
            if key in used: continue
            if rank >= RESERVE: break
            used.add(key); rank += 1
            cid = "S18-" + hashlib.sha256(f"{fam}|{g['graph']}|{g['gold_cypher']}".encode()).hexdigest()[:10]
            cands.append({"case_id": cid, "family": fam, "rank": rank, **g, "rewrite_cypher": rw})
    return gold, cands

def main():
    ct_dir, out = sys.argv[1], sys.argv[2]
    gold, cands = build(ct_dir)
    with open(out, "w") as f:
        for c in cands: f.write(json.dumps(c) + "\n")
    from collections import Counter
    print(json.dumps({"distinct_gold": len(gold), "eligible_per_family": {f: len([1 for g in gold if (RULES[f](g["gold_cypher"]) or g["gold_cypher"]) != g["gold_cypher"]]) for f in FAMILIES},
                      "candidates_per_family": Counter(c["family"] for c in cands),
                      "sha256": hashlib.sha256(open(out, "rb").read()).hexdigest()}, indent=1, default=dict))

if __name__ == "__main__":
    main()
