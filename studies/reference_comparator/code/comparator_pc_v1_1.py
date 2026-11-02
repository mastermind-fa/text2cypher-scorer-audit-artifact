"""
comparator_pc_v1_1.py -- versioned repair of the the pilot stage frozen pilot comparator (VERSION = "pc-v1.1")
pc-v1.1 = pc-v1.0 (archive/provenance_recovered_2026-10-02/session7_code/comparator.py, sha 13aa6fb9..., preserved
unchanged) + ONE change (D-S9B-06): type_sensitive returns False when gold and prediction row widths differ (both
directions), instead of crashing (prediction narrower) or comparing a gold-width column prefix (prediction wider).
primary, positional_strict, sorted_string_exact, set_equality and all helpers are byte-identical to pc-v1.0.
Primary comparator for SQL-oracle vs Cypher-result comparison, plus C3 alternatives.
Results are lists of rows; a row is a dict (column -> value) or a list/tuple of values.
See comparator_spec.md for the policy. Do NOT edit without bumping VERSION.
"""
import itertools, math, json

VERSION = "pc-v1.1"
REL_TOL, ABS_TOL = 1e-6, 1e-9
MAX_PERM_COLS = 6  # column-permutation search bound (6! = 720)


# ---------- value normalisation ----------
def _graph_obj(v):
    """Serialise Neo4j node/relationship/path-like objects (dicts with element/labels keys) deterministically."""
    return json.dumps(v, sort_keys=True, default=str)


def norm_value(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return ("bool", v)
    if isinstance(v, (int, float)):
        return ("num", float(v))
    if isinstance(v, str):
        return ("str", v)
    if isinstance(v, (list, tuple)):
        return ("list", tuple(norm_value(x) for x in v))
    if isinstance(v, dict):
        return ("obj", _graph_obj(v))
    return ("str", str(v))


def values_equal(a, b, type_sensitive=False, orig=None):
    if a is None or b is None:
        return a is None and b is None
    if a[0] != b[0]:
        return False
    if a[0] == "num":
        if type_sensitive and orig is not None and type(orig[0]) is not type(orig[1]):
            return False
        x, y = a[1], b[1]
        if math.isnan(x) or math.isnan(y):
            return math.isnan(x) and math.isnan(y)
        return math.isclose(x, y, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    if a[0] == "list":
        return len(a[1]) == len(b[1]) and all(values_equal(p, q) for p, q in zip(a[1], b[1]))
    return a[1] == b[1]


def row_values(r):
    return list(r.values()) if isinstance(r, dict) else list(r)


# ---------- core multiset matching ----------
def _multiset_match(ref, pred, perm, type_sensitive):
    used = [False] * len(pred)
    for rr in ref:
        rv = row_values(rr); ok = False
        for j, pr in enumerate(pred):
            if used[j]:
                continue
            pv = row_values(pr)
            pv = [pv[i] for i in perm]
            if len(pv) != len(rv):
                continue
            if all(values_equal(norm_value(a), norm_value(b), type_sensitive, (a, b)) for a, b in zip(rv, pv)):
                used[j] = True; ok = True; break
        if not ok:
            return False
    return True


def _perms(n):
    if n > MAX_PERM_COLS:
        return [tuple(range(n))]
    return list(itertools.permutations(range(n)))


# ---------- public comparators ----------
def primary(ref, pred):
    """pc-v1.0 PRIMARY. Order-insensitive multiset equality with numeric tolerance, int/float coerced,
    column names ignored, column order matched by the best bijection (<=6 cols).
    Returns (match: bool, flags: list[str])."""
    flags = []
    if ref is None:
        return None, ["REFERENCE_MISSING_EXCLUDE"]          # never score missing gold as empty
    if pred is None:
        return False, ["PREDICTION_ERROR_OR_TIMEOUT"]
    if len(ref) == 0:
        flags.append("EMPTY_REFERENCE_VACUOUS")
    if len(ref) == 1 and all(v is None for v in row_values(ref[0])):
        flags.append("ALL_NULL_REFERENCE_VACUOUS")
    if len(ref) != len(pred):
        return False, flags + ["ROW_COUNT_MISMATCH"]
    if len(ref) == 0:
        return True, flags
    nr, np_ = len(row_values(ref[0])), len(row_values(pred[0]))
    if nr != np_:
        return False, flags + ["ARITY_MISMATCH"]
    for perm in _perms(nr):
        if _multiset_match(ref, pred, perm, type_sensitive=False):
            if perm != tuple(range(nr)):
                flags.append("COLUMN_PERMUTED")
            return True, flags
    return False, flags + ["VALUE_MISMATCH"]


def positional_strict(ref, pred):
    """C3 variant: row order and column order matter, exact equality (no tolerance)."""
    if ref is None or pred is None:
        return None if ref is None else False
    return [row_values(r) for r in ref] == [row_values(p) for p in pred]


def sorted_string_exact(ref, pred):
    """C3 variant approximating Text2Cypher practice: stringify rows, sort lexicographically, compare exactly."""
    if ref is None or pred is None:
        return None if ref is None else False
    s = lambda rows: sorted(json.dumps(row_values(r), default=str) for r in rows)
    return s(ref) == s(pred)


def type_sensitive(ref, pred):
    """C3 variant: like primary but int vs float counts as a mismatch."""
    if ref is None or pred is None:
        return None if ref is None else False
    if len(ref) != len(pred):
        return False
    if not ref:
        return True
    # pc-v1.1 arity guard (D-S9B-06): different result arity is not equality. Widths are checked on BOTH sides and on
    # every row (no width inferred from one side), mirroring the ARITY_MISMATCH rule of primary().
    widths = {len(row_values(r)) for r in ref} | {len(row_values(p)) for p in pred}
    if len(widths) != 1:
        return False
    n = len(row_values(ref[0]))
    return any(_multiset_match(ref, pred, p, type_sensitive=True) for p in _perms(n))


def set_equality(ref, pred):
    """C3 variant (LAST-CQ style): set of canonicalised rows, duplicates ignored; empty-vs-empty = match."""
    if ref is None or pred is None:
        return None if ref is None else False
    canon = lambda rows: {json.dumps(sorted(norm_value(v) for v in row_values(r) if v is not None) +
                                     [None] * sum(v is None for v in row_values(r)), default=str) for r in rows}
    return canon(ref) == canon(pred)


ALL = {"primary": lambda r, p: primary(r, p)[0], "positional_strict": positional_strict,
       "sorted_string_exact": sorted_string_exact, "type_sensitive": type_sensitive, "set_equality": set_equality}
