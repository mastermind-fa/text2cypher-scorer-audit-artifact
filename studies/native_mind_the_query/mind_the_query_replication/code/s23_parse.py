#!/usr/bin/env python3
"""study S23 — Cypher final-RETURN parser for Mind the Query gold queries (s23-parse-v1). OFFLINE, pure functions.

The frozen study S18 parser (s18_rewrite.parse_return) requires the RETURN clause to start a line; Mind the Query
gold queries are mostly single-line, so S23 uses this separate, string- and bracket-aware tokenizer. S18 code is not
modified. Supported shape: exactly one RETURN keyword outside string literals, no UNION / CALL, and a tail after the
RETURN items made only of ORDER BY / SKIP / LIMIT at bracket depth 0.

  split_query(q) -> {"head", "distinct", "items", "order_by", "skip_limit"} or None
  rebuild(p)     -> query text
  item_alias(it) -> (expression, alias or None)
  column_name(it)-> the column name Neo4j reports for the item (alias, else the expression text as written)
"""
import re

_KW = re.compile(r"\b(RETURN|UNION|CALL|ORDER\s+BY|SKIP|LIMIT)\b", re.I)


def _mask(q):
    """Copy of q with string-literal / backtick contents replaced by '_' and bracket depth per position."""
    out, depth, quote = [], [], None
    d = 0
    for ch in q:
        if quote:
            out.append(ch if ch == quote else "_")
            if ch == quote: quote = None
            depth.append(d); continue
        if ch in "'\"`":
            quote = ch; out.append(ch); depth.append(d); continue
        if ch in "([{": d += 1
        depth.append(d)
        if ch in ")]}": d -= 1
        out.append(ch)
    return "".join(out), depth, quote is None and d == 0


def split_top(s):
    out, depth, cur, q = [], 0, [], None
    for ch in s:
        if q:
            cur.append(ch); q = None if ch == q else q; continue
        if ch in "'\"`": q = ch
        elif ch in "([{": depth += 1
        elif ch in ")]}": depth -= 1
        if ch == "," and depth == 0: out.append("".join(cur).strip()); cur = []
        else: cur.append(ch)
    if "".join(cur).strip(): out.append("".join(cur).strip())
    return out


def split_query(q):
    masked, depth, balanced = _mask(q)
    if not balanced: return None
    kws = [(m.start(), m.end(), re.sub(r"\s+", " ", m.group(1).upper())) for m in _KW.finditer(masked)
           if depth[m.start()] == 0]
    rets = [k for k in kws if k[2] == "RETURN"]
    if len(rets) != 1 or any(k[2] in ("UNION", "CALL") for k in kws): return None
    if len(re.findall(r"\bRETURN\b", masked, re.I)) != 1: return None
    r0, r1, _ = rets[0]
    after = [k for k in kws if k[0] > r0 and k[2] != "RETURN"]
    body_end = after[0][0] if after else len(q)
    body = q[r1:body_end].strip()
    distinct = bool(re.match(r"DISTINCT\b", body, re.I))
    if distinct: body = body[len("DISTINCT"):].strip()
    items = split_top(body)
    if not items or any(not i for i in items): return None
    order_by, skip_limit = None, []
    for i, (s, e, kw) in enumerate(after):
        nxt = after[i + 1][0] if i + 1 < len(after) else len(q)
        arg = q[e:nxt].strip()
        if not arg: return None
        if kw == "ORDER BY":
            if order_by is not None or skip_limit: return None
            order_by = arg
        else:
            skip_limit.append(f"{kw} {arg}")
    return {"head": q[:r0].strip(), "distinct": distinct, "items": items, "order_by": order_by,
            "skip_limit": skip_limit}


def rebuild(p):
    s = (p["head"] + " " if p["head"] else "") + "RETURN " + ("DISTINCT " if p["distinct"] else "") + ", ".join(p["items"])
    if p["order_by"]: s += " ORDER BY " + p["order_by"]
    if p["skip_limit"]: s += " " + " ".join(p["skip_limit"])
    return s


def item_alias(it):
    m = re.match(r"^(.*?)\s+AS\s+([A-Za-z_][A-Za-z0-9_]*|`[^`]+`)$", it, re.S | re.I)
    if m: return m.group(1).strip(), m.group(2)
    return it.strip(), None


def column_name(it):
    e, a = item_alias(it)
    if a is None: return e
    return a[1:-1] if a.startswith("`") else a


def as_item(expr, name):
    """expr projected under the exact column name `name` (backtick alias when name is not a plain identifier)."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name): return f"{expr} AS {name}"
    if "`" in name: return None
    return f"{expr} AS `{name}`"


def has_order_skip_limit_anywhere(q):
    masked, _, _ = _mask(q)
    return bool(re.search(r"\b(ORDER\s+BY|SKIP|LIMIT)\b", masked, re.I))


def count_order_by(q):
    masked, _, _ = _mask(q)
    return len(re.findall(r"\bORDER\s+BY\b", masked, re.I))


def normalise_source(q):
    """Representation-only source normalisation (pre-declared): strip whitespace and one trailing ';'."""
    q = q.strip()
    if q.endswith(";"): q = q[:-1].rstrip()
    return q
