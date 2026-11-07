#!/usr/bin/env python3
"""Does insert_to_neo4j.py, applied to a Works-Cycles SQLite file, produce the experimental graph G0? Read-only; no Neo4j.

  python3 predict_graph_fingerprint.py /path/to/works_cycles.sqlite

Reads TABLE_PKS and FOREIGN_KEYS from the converter's syntax tree (the module is not imported or executed), applies its
load semantics to database/works_cycles.sqlite in Python, and compares the predicted per-label node counts and
per-type relationship counts with the frozen G0 fingerprint (expected_G0_fingerprint.json).
Emulated semantics: one node per distinct primary-key tuple per table (MERGE on the PK map); for each FK definition,
rows with a non-NULL FK, MATCH source by its PK and target by (label, PK property = FK value) with Cypher-like equality
(int == float; string != number), MERGE one relationship per distinct (source, type, target)."""
import ast, collections, hashlib, json, os, sqlite3

import sys
HERE = os.path.dirname(os.path.abspath(__file__))
CONV = os.path.join(HERE, "insert_to_neo4j.py")
DB = sys.argv[1] if len(sys.argv) > 1 else "works_cycles.sqlite"
FP = os.path.join(HERE, "expected_G0_fingerprint.json")


def literal(name):
    tree = ast.parse(open(CONV).read())
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            return ast.literal_eval(n.value)
    raise KeyError(name)


def key(v):  # Cypher equality class: numbers compare by value, strings by text, types never mix
    if isinstance(v, bool): return ("b", v)
    if isinstance(v, (int, float)): return ("n", float(v))
    return ("s", v)


def main():
    pks, fks = literal("TABLE_PKS"), literal("FOREIGN_KEYS")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    nodes, index = {}, {}
    for t, pk in pks.items():
        cols = pk if isinstance(pk, list) else [pk]
        try:
            rows = con.execute(f'SELECT {", ".join(chr(34)+c+chr(34) for c in cols)} FROM "{t}"').fetchall()
        except sqlite3.Error:
            continue  # the converter skips missing tables the same way
        keys = {tuple(key(v) for v in r) for r in rows}
        nodes[t] = len(keys); index[t] = keys
    # per-table lookup of single PK columns (target match is on ONE property)
    prop_values = {}
    def values_of(t, col):
        if (t, col) not in prop_values:
            prop_values[(t, col)] = collections.Counter(key(v) for (v,) in con.execute(f'SELECT DISTINCT "{col}" FROM "{t}"'))
        return prop_values[(t, col)]
    rels = collections.Counter()
    for ft, fk, tt, tpk, lab in fks:
        if ft not in index or tt not in index: continue
        fpk = pks[ft] if isinstance(pks[ft], list) else [pks[ft]]
        sel = list(fpk) + ([fk] if fk not in fpk else [])
        try:
            rows = con.execute(f'SELECT {", ".join(chr(34)+c+chr(34) for c in sel)} FROM "{ft}" WHERE "{fk}" IS NOT NULL').fetchall()
        except sqlite3.Error:
            continue
        tgt = values_of(tt, tpk)
        pairs = set()
        for r in rows:
            d = dict(zip(sel, r)); src = tuple(key(d[c]) for c in fpk); v = key(d[fk])
            if v in tgt:  # a target node exists with that property value (distinct targets counted via value)
                pairs.add((src, v))
        rels[f"{lab}|{ft}->{tt}"] += len(pairs)
    fp = json.load(open(FP))
    fn, fr = fp["nodes"], fp.get("relationships") or fp.get("rels") or {}
    node_diff = {l: (nodes.get(l, 0), fn.get(l, 0)) for l in set(nodes) | set(fn) if nodes.get(l, 0) != fn.get(l, 0)}
    rel_diff = {l: (rels.get(l, 0), fr.get(l, 0)) for l in set(rels) | set(fr) if rels.get(l, 0) != fr.get(l, 0)}
    res = {           "sqlite_sha256": hashlib.sha256(open(DB, "rb").read()).hexdigest(),
           "fingerprint_keys": list(fp.keys()),
           "predicted": {"labels": sum(1 for v in nodes.values() if v), "nodes": sum(nodes.values()),
                         "rel_types": sum(1 for v in rels.values() if v), "relationships": sum(rels.values())},
           "frozen_G0": {"labels": sum(1 for v in fn.values() if v), "nodes": sum(fn.values()),
                         "rel_types": sum(1 for v in fr.values() if v), "relationships": sum(fr.values())},
           "node_count_differences": node_diff, "relationship_count_differences": rel_diff,
           "fk_definitions": len(fks), "tables": len(pks)}
    print(json.dumps(res, indent=1, default=str))
    ok = not node_diff and not rel_diff
    print("OFFLINE GRAPH PREDICTION:", "MATCHES the frozen G0 fingerprint" if ok else "DIFFERS from the frozen G0 fingerprint")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
