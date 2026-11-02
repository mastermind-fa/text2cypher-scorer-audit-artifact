#!/usr/bin/env python3
"""MAIN_AUDIT S1 — deterministic metamorphic result-pair suite (audit-s1-v1).

Builds hand-specified result-pair fixtures with a by-construction expected interpretation. NO scorer is imported or
run here; NO model, database or network is used. The suite is frozen (hash recorded in S1_MANIFEST.json) BEFORE any
scorer is run on it (protocol: internal project records (not released) §P5).

Oracle labels (canonical value-semantic interpretation, rules R1–R12 in the protocol):
  EQUIV            same answer to the question under the canonical rules
  NONEQUIV         different answer
  INTENT_DEPENDENT the answer depends on question intent (bag vs set, unspecified collect() order, tie breaks,
                   extra projected columns); reported descriptively, never counted as a scorer error.

Usage: python3 build_s1.py            -> writes s1_cases.jsonl + S1_MANIFEST.json next to this file
"""
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE_ID = "audit-s1-v1"

# ---------------------------------------------------------------------------------------------------------------
# Base results. Each: (query, ordered column list, rows as lists). Synthetic product-catalogue domain; no project
# gold content is used.
B = {
    "B1": ("MATCH (p:Product) RETURN count(p) AS n_products", ["n_products"], [[3]]),
    "B2": ("MATCH (p:Product) RETURN p.name AS name", ["name"], [["Bolt"], ["Chain"], ["Wheel"]]),
    "B3": ("MATCH (p:Product) RETURN p.name AS name, p.stock AS stock", ["name", "stock"],
           [["Bolt", 40], ["Chain", 12], ["Wheel", 7]]),
    "B4": ("MATCH (p:Product) RETURN p.name AS name, p.stock AS stock, p.price AS price", ["name", "stock", "price"],
           [["Bolt", 40, 0.5], ["Chain", 12, 9.75], ["Wheel", 7, 31.2]]),
    "B5": ("MATCH (p:Product)-[:MADE_BY]->(v:Vendor) RETURN p.name AS name, p.stock AS stock, p.price AS price, "
           "v.name AS vendor", ["name", "stock", "price", "vendor"],
           [["Bolt", 40, 0.5, "Acme"], ["Chain", 12, 9.75, "Bexa"], ["Wheel", 7, 31.2, "Acme"]]),
    "B6": ("MATCH (p:Product) RETURN p.name AS name, p.stock AS stock ORDER BY p.stock DESC LIMIT 3",
           ["name", "stock"], [["Bolt", 40], ["Chain", 12], ["Wheel", 7]]),
}

# Cypher-style default keys for unaliased RETURN expressions (what Neo4j returns when no alias is given).
UNALIASED = {"n_products": "count(p)", "name": "p.name", "stock": "p.stock", "price": "p.price",
             "vendor": "v.name"}


def rows_to_dicts(cols, rows):
    return [dict(zip(cols, r)) for r in rows]


CASES = []


def add(dim, base, expected, rule, notes, ref_cols, ref_rows, pred_cols, pred_rows, ref_query=None,
        pred_query=None):
    """Register one case. Rows are lists aligned with the column lists; stored as ordered dicts (JSON objects keep
    insertion order, which is the column order a driver would return)."""
    rq = ref_query if ref_query is not None else B[base][0] if base else "MATCH (x) RETURN x"
    pq = pred_query if pred_query is not None else rq.replace("MATCH (p:Product)", "MATCH (q:Product)") \
        .replace("p.", "q.").replace("count(p)", "count(q)")
    CASES.append({
        "case_id": f"S1-{len(CASES) + 1:03d}",
        "dimension": dim,
        "base": base,
        "ref_query": rq,
        "pred_query": pq,
        "ref_columns": ref_cols,
        "pred_columns": pred_cols,
        "reference_result": rows_to_dicts(ref_cols, ref_rows),
        "predicted_result": rows_to_dicts(pred_cols, pred_rows),
        "expected": expected,
        "rule": rule,
        "notes": notes,
    })


def base(b):
    q, c, r = B[b]
    return q, list(c), [list(x) for x in r]


# D01 identical ------------------------------------------------------------------------------------------------
for b in B:
    q, c, r = base(b)
    add("D01_identical", b, "EQUIV", "R1", "identical result", c, r, c, r)

# D02 alias renamed (different explicit aliases) ---------------------------------------------------------------
for b in B:
    q, c, r = base(b)
    add("D02_alias_renamed", b, "EQUIV", "R2", "same values, different explicit aliases", c, r,
        [x + "_alias" for x in c], r)

# D03 Cypher unaliased expression keys vs aliased gold ---------------------------------------------------------
for b in B:
    q, c, r = base(b)
    add("D03_unaliased_expression_keys", b, "EQUIV", "R2",
        "prediction RETURNs expressions without AS, so keys are e.g. 'p.name' / 'count(p)'", c, r,
        [UNALIASED[x] for x in c], r)

# D04 column order permuted -------------------------------------------------------------------------------------
for b, perm in [("B3", [1, 0]), ("B4", [2, 0, 1]), ("B4", [1, 2, 0]), ("B5", [3, 2, 1, 0]), ("B5", [1, 0, 3, 2]),
                ("B6", [1, 0])]:
    q, c, r = base(b)
    add("D04_column_order", b, "EQUIV" if b != "B6" else "EQUIV", "R3", f"columns permuted {perm}", c, r,
        [c[i] for i in perm], [[row[i] for i in perm] for row in r])

# D05 row permutation, no ORDER BY anywhere --------------------------------------------------------------------
for b in ["B2", "B3", "B4", "B5"]:
    q, c, r = base(b)
    add("D05_row_order_unordered", b, "EQUIV", "R4", "rows reversed; neither query orders", c, r, c, r[::-1])
q, c, r = base("B3")
add("D05_row_order_unordered", "B3", "EQUIV", "R4", "rows rotated; neither query orders", c, r, c, r[1:] + r[:1])

# D06 gold ORDER BY, prediction unordered with different order --------------------------------------------------
q, c, r = base("B6")
unord = "MATCH (q:Product) RETURN q.name AS name, q.stock AS stock"
add("D06_order_required_violated", "B6", "NONEQUIV", "R5", "gold orders; prediction lacks ORDER BY, order differs",
    c, r, c, r[::-1], pred_query=unord + " LIMIT 3")
add("D06_order_required_violated", "B6", "NONEQUIV", "R5", "gold orders; prediction lacks ORDER BY, rotated",
    c, r, c, r[1:] + r[:1], pred_query=unord + " LIMIT 3")
add("D06_order_required_violated", "B6", "NONEQUIV", "R5",
    "gold orders DESC; prediction orders ASC (also has ORDER BY)", c, r, c, r[::-1],
    pred_query=unord + " ORDER BY q.stock ASC LIMIT 3")
add("D06_order_required_violated", "B6", "NONEQUIV", "R5", "gold orders; prediction swaps first two rows only",
    c, r, c, [r[1], r[0], r[2]], pred_query=unord + " LIMIT 3")

# D07 prediction ORDER BY, gold unordered, different order --------------------------------------------------------
for b in ["B2", "B3", "B4"]:
    q, c, r = base(b)
    add("D07_order_not_required", b, "EQUIV", "R4", "prediction orders, gold does not; order differs", c, r,
        c, r[::-1], pred_query=f"MATCH (q:Product) RETURN q.name AS name ORDER BY q.name DESC")
q, c, r = base("B3")
add("D07_order_not_required", "B3", "EQUIV", "R4", "prediction orders by stock, gold unordered", c, r, c,
    sorted(r, key=lambda x: x[1]), pred_query="MATCH (q:Product) RETURN q.name AS name, q.stock AS stock "
                                                "ORDER BY q.stock")

# D08 both ordered, same order (control) ------------------------------------------------------------------------
q, c, r = base("B6")
add("D08_order_both_same", "B6", "EQUIV", "R5", "both ORDER BY, same order", c, r, c, r,
    pred_query="MATCH (q:Product) RETURN q.name AS name, q.stock AS stock ORDER BY q.stock DESC LIMIT 3")
add("D08_order_both_same", "B6", "EQUIV", "R5", "both ORDER BY, same order, aliases differ", c, r,
    ["product", "units"], r,
    pred_query="MATCH (q:Product) RETURN q.name AS product, q.stock AS units ORDER BY q.stock DESC LIMIT 3")

# D09 duplicates ---------------------------------------------------------------------------------------------------
for b in ["B2", "B3", "B4", "B5"]:
    q, c, r = base(b)
    add("D09_duplicate_extra_in_pred", b, "INTENT_DEPENDENT", "R6", "prediction repeats first row (bag vs set)",
        c, r, c, r + [r[0]])
for b in ["B2", "B3"]:
    q, c, r = base(b)
    add("D09_duplicate_removed_in_pred", b, "INTENT_DEPENDENT", "R6",
        "gold contains a duplicate row; prediction is DISTINCT", c, r + [r[0]], c, r)
q, c, r = base("B2")
add("D09_duplicate_multiplicity_differs", "B2", "INTENT_DEPENDENT", "R6",
    "same row-set, different multiplicities (gold A,A,B vs pred A,B,B)", c, [r[0], r[0], r[1]], c,
    [r[0], r[1], r[1]])

# D10 extra row / D11 missing row ----------------------------------------------------------------------------------
for b in ["B2", "B3", "B4", "B5", "B6"]:
    q, c, r = base(b)
    extra = list(r[0]); extra[0] = "Spoke"
    add("D10_extra_row", b, "NONEQUIV", "R7", "prediction has one additional distinct row", c, r, c, r + [extra])
for b in ["B2", "B3", "B4", "B5", "B6"]:
    q, c, r = base(b)
    add("D11_missing_row", b, "NONEQUIV", "R7", "prediction lacks the last row", c, r, c, r[:-1])

# D12 int vs float, equal value -------------------------------------------------------------------------------------
q, c, r = base("B1")
add("D12_int_vs_float", "B1", "EQUIV", "R8", "3 vs 3.0", c, r, c, [[3.0]])
add("D12_int_vs_float", "B1", "EQUIV", "R8", "3.0 (gold) vs 3 (pred)", c, [[3.0]], c, r)
q, c, r = base("B3")
add("D12_int_vs_float", "B3", "EQUIV", "R8", "stock as float in prediction", c, r, c, [[x[0], float(x[1])] for x in r])
q, c, r = base("B4")
add("D12_int_vs_float", "B4", "EQUIV", "R8", "integral price stored as int in gold, float in pred", c,
    [[x[0], x[1], 2] for x in r], c, [[x[0], x[1], 2.0] for x in r])

# D13 numeric tolerance ----------------------------------------------------------------------------------------------
q, c, r = base("B4")
add("D13_float_tolerance_tiny", "B4", "EQUIV", "R9", "0.1+0.2 vs 0.3 (float rounding, |d|~5.6e-17)", c,
    [[x[0], x[1], 0.3] for x in r], c, [[x[0], x[1], 0.1 + 0.2] for x in r])
add("D13_float_tolerance_tiny", "B4", "EQUIV", "R9", "relative difference 1e-12", c, r, c,
    [[x[0], x[1], x[2] * (1 + 1e-12)] for x in r])
q, c, r = base("B1")
add("D13_float_tolerance_tiny", "B1", "EQUIV", "R9", "average 2.6666666666666665 vs 2.666666666666667", c,
    [[2.6666666666666665]], c, [[2.666666666666667]])
add("D13_float_tolerance_tiny", "B1", "EQUIV", "R9", "SUM float drift 272958.0 vs 272958.00000000006", c,
    [[272958.0]], c, [[272958.00000000006]])
q, c, r = base("B4")
add("D13_float_difference_material", "B4", "NONEQUIV", "R9", "price differs by 1e-3 absolute", c, r, c,
    [[x[0], x[1], round(x[2] + 0.001, 6)] for x in r])
q, c, r = base("B1")
add("D13_float_difference_material", "B1", "NONEQUIV", "R9", "2.67 (rounded) vs 2.6666666666666665", c,
    [[2.6666666666666665]], c, [[2.67]])
add("D13_float_difference_material", "B1", "NONEQUIV", "R9", "3 vs 3.5", c, [[3]], c, [[3.5]])

# D14 number vs numeric string ------------------------------------------------------------------------------------
q, c, r = base("B1")
add("D14_number_vs_string", "B1", "NONEQUIV", "R10", "3 vs '3'", c, r, c, [["3"]])
add("D14_number_vs_string", "B1", "NONEQUIV", "R10", "'3' (gold) vs 3", c, [["3"]], c, r)
add("D14_number_vs_string", "B1", "NONEQUIV", "R10", "3.0 vs '3.0'", c, [[3.0]], c, [["3.0"]])
q, c, r = base("B3")
add("D14_number_vs_string", "B3", "NONEQUIV", "R10", "stock as strings in prediction", c, r, c,
    [[x[0], str(x[1])] for x in r])

# D15 NULL vs empty string / 0 ----------------------------------------------------------------------------------------
q, c, r = base("B3")
add("D15_null_vs_empty_string", "B3", "NONEQUIV", "R11", "None vs '' in one cell", c, [["Bolt", None]] + r[1:],
    c, [["Bolt", ""]] + r[1:])
add("D15_null_vs_empty_string", "B3", "NONEQUIV", "R11", "'' (gold) vs None", c, [["Bolt", ""]] + r[1:], c,
    [["Bolt", None]] + r[1:])
add("D15_null_vs_zero", "B3", "NONEQUIV", "R11", "None vs 0", c, [["Bolt", None]] + r[1:], c, [["Bolt", 0]] + r[1:])
add("D15_null_vs_string_none", "B3", "NONEQUIV", "R11", "None vs 'None' string", c, [["Bolt", None]] + r[1:], c,
    [["Bolt", "None"]] + r[1:])

# D16 NULL in permuted unordered rows ------------------------------------------------------------------------------
q, c, r = base("B3")
rn = [["Bolt", None]] + r[1:]
add("D16_null_row_permutation", "B3", "EQUIV", "R4", "row with NULL moved; unordered", c, rn, c, rn[::-1])
add("D16_null_row_permutation", "B3", "EQUIV", "R4", "two NULL cells, rows rotated", c,
    [["Bolt", None], ["Chain", None], ["Wheel", 7]], c, [["Chain", None], ["Wheel", 7], ["Bolt", None]])

# D17 empty results -----------------------------------------------------------------------------------------------
c = ["name"]
add("D17_both_empty", "B2", "EQUIV", "R12", "both empty (vacuous agreement; value-identical)", c, [], c, [])
add("D17_both_empty", "B3", "EQUIV", "R12", "both empty, different projected columns", ["name", "stock"], [],
    ["p.name"], [])
q, c, r = base("B2")
add("D17_gold_empty_pred_nonempty", "B2", "NONEQUIV", "R7", "gold empty, prediction returns rows", c, [], c, r)
add("D17_gold_empty_pred_nonempty", "B1", "NONEQUIV", "R7", "gold empty, prediction returns count 0",
    ["n_products"], [], ["n_products"], [[0]])
add("D17_gold_nonempty_pred_empty", "B2", "NONEQUIV", "R7", "gold rows, prediction empty", c, r, c, [])
add("D17_gold_nonempty_pred_empty", "B1", "NONEQUIV", "R7", "gold count, prediction empty", ["n_products"], [[3]],
    ["n_products"], [])

# D18 zero-valued aggregates ---------------------------------------------------------------------------------------
add("D18_zero_aggregate", "B1", "EQUIV", "R2", "0 vs 0 with different alias", ["n_products"], [[0]],
    ["count(q)"], [[0]])
add("D18_zero_aggregate", "B1", "EQUIV", "R8", "0 vs 0.0", ["total"], [[0]], ["total"], [[0.0]])
add("D18_zero_aggregate", "B1", "NONEQUIV", "R7", "0 vs empty result", ["total"], [[0]], ["total"], [])
add("D18_zero_aggregate", "B1", "NONEQUIV", "R11", "0 vs NULL (SUM over empty set)", ["total"], [[0]], ["total"],
    [[None]])

# D19 all-NULL results -----------------------------------------------------------------------------------------------
add("D19_all_null", "B1", "EQUIV", "R2", "single NULL vs single NULL, different alias", ["x"], [[None]], ["y"],
    [[None]])
add("D19_all_null", "B3", "EQUIV", "R1", "all-NULL two-column row, identical", ["a", "b"], [[None, None]],
    ["a", "b"], [[None, None]])
add("D19_all_null", "B1", "NONEQUIV", "R7", "all-NULL vs empty result", ["x"], [[None]], ["x"], [])
add("D19_all_null", "B3", "NONEQUIV", "R7", "two NULL rows vs one NULL row", ["x"], [[None], [None]], ["x"],
    [[None]])

# D20 string formatting -----------------------------------------------------------------------------------------------
q, c, r = base("B2")
add("D20_string_case", "B2", "NONEQUIV", "R10", "case differs ('bolt')", c, r, c, [["bolt"]] + r[1:])
add("D20_string_case", "B2", "NONEQUIV", "R10", "all upper case", c, r, c, [[x[0].upper()] for x in r])
add("D20_string_whitespace", "B2", "NONEQUIV", "R10", "trailing space", c, r, c, [["Bolt "]] + r[1:])
add("D20_string_whitespace", "B2", "NONEQUIV", "R10", "leading space", c, r, c, [[" Bolt"]] + r[1:])

# D21 list values (collect) --------------------------------------------------------------------------------------------
lc = ["vendor", "products"]
add("D21_list_identical", None, "EQUIV", "R1", "identical collected lists", lc, [["Acme", ["Bolt", "Wheel"]]], lc,
    [["Acme", ["Bolt", "Wheel"]]], ref_query="MATCH (v:Vendor)<-[:MADE_BY]-(p) RETURN v.name AS vendor, "
                                             "collect(p.name) AS products")
add("D21_list_identical", None, "EQUIV", "R2", "identical lists, unaliased keys", lc,
    [["Acme", ["Bolt", "Wheel"]]], ["v.name", "collect(p.name)"], [["Acme", ["Bolt", "Wheel"]]],
    ref_query="MATCH (v:Vendor)<-[:MADE_BY]-(p) RETURN v.name AS vendor, collect(p.name) AS products")
add("D21_list_order", None, "INTENT_DEPENDENT", "R6", "same elements, different collect() order", lc,
    [["Acme", ["Bolt", "Wheel"]]], lc, [["Acme", ["Wheel", "Bolt"]]],
    ref_query="MATCH (v:Vendor)<-[:MADE_BY]-(p) RETURN v.name AS vendor, collect(p.name) AS products")
add("D21_list_order", None, "INTENT_DEPENDENT", "R6", "numeric list, different order", ["v", "stocks"],
    [["Acme", [40, 7]]], ["v", "stocks"], [["Acme", [7, 40]]],
    ref_query="MATCH (v:Vendor)<-[:MADE_BY]-(p) RETURN v.name AS v, collect(p.stock) AS stocks")
add("D21_list_order", None, "INTENT_DEPENDENT", "R6", "list with duplicate elements reordered", ["v", "xs"],
    [["Acme", [1, 1, 2]]], ["v", "xs"], [["Acme", [2, 1, 1]]],
    ref_query="MATCH (v:Vendor)<-[:MADE_BY]-(p) RETURN v.name AS v, collect(p.batch) AS xs")
add("D21_list_different", None, "NONEQUIV", "R7", "missing list element", lc, [["Acme", ["Bolt", "Wheel"]]], lc,
    [["Acme", ["Bolt"]]], ref_query="MATCH (v:Vendor)<-[:MADE_BY]-(p) RETURN v.name AS vendor, "
                                    "collect(p.name) AS products")
add("D21_list_different", None, "NONEQUIV", "R7", "list vs scalar", lc, [["Acme", ["Bolt"]]], lc,
    [["Acme", "Bolt"]], ref_query="MATCH (v:Vendor)<-[:MADE_BY]-(p) RETURN v.name AS vendor, "
                                  "collect(p.name) AS products")

# D22 map values (property maps, as node properties are often serialised) -----------------------------------------
mc = ["product"]
mq = "MATCH (p:Product {name:'Bolt'}) RETURN p {.name, .stock} AS product"
add("D22_map_identical", None, "EQUIV", "R1", "identical maps", mc, [[{"name": "Bolt", "stock": 40}]], mc,
    [[{"name": "Bolt", "stock": 40}]], ref_query=mq)
add("D22_map_key_order", None, "EQUIV", "R3", "same map, different key insertion order", mc,
    [[{"name": "Bolt", "stock": 40}]], mc, [[{"stock": 40, "name": "Bolt"}]], ref_query=mq)
add("D22_map_different", None, "NONEQUIV", "R7", "map value differs", mc, [[{"name": "Bolt", "stock": 40}]], mc,
    [[{"name": "Bolt", "stock": 41}]], ref_query=mq)
add("D22_map_vs_scalar", None, "NONEQUIV", "R7", "map vs its name property", mc, [[{"name": "Bolt", "stock": 40}]],
    mc, [["Bolt"]], ref_query=mq)

# D23 tied top-k ---------------------------------------------------------------------------------------------------
tc = ["name", "stock"]
tq = "MATCH (p:Product) RETURN p.name AS name, p.stock AS stock ORDER BY p.stock DESC LIMIT 2"
add("D23_topk_tie", None, "INTENT_DEPENDENT", "R5", "tie at LIMIT boundary; prediction returns the other tied row",
    tc, [["Bolt", 40], ["Chain", 12]], tc, [["Bolt", 40], ["Gear", 12]], ref_query=tq,
    pred_query=tq.replace("p.", "q.").replace("(p:", "(q:"))
add("D23_topk_tie", None, "INTENT_DEPENDENT", "R5", "full tie: two rows with equal sort key, swapped order", tc,
    [["Chain", 12], ["Gear", 12]], tc, [["Gear", 12], ["Chain", 12]], ref_query=tq,
    pred_query=tq.replace("p.", "q.").replace("(p:", "(q:"))
add("D23_topk_tie", None, "INTENT_DEPENDENT", "R5", "tie inside top-k, different order, prediction unordered", tc,
    [["Bolt", 40], ["Chain", 12], ["Gear", 12]], tc, [["Bolt", 40], ["Gear", 12], ["Chain", 12]],
    ref_query=tq.replace("LIMIT 2", "LIMIT 3"), pred_query="MATCH (q:Product) RETURN q.name AS name, "
                                                           "q.stock AS stock LIMIT 3")

# D24 extra / missing projected column ----------------------------------------------------------------------------
q, c, r = base("B3")
add("D24_extra_column", "B3", "INTENT_DEPENDENT", "R13", "prediction adds a correct extra column (price)", c, r,
    ["name", "stock", "price"], [x + [p] for x, p in zip(r, [0.5, 9.75, 31.2])])
add("D24_extra_column", "B2", "INTENT_DEPENDENT", "R13", "prediction adds an id column", ["name"],
    [[x[0]] for x in r], ["id", "name"], [[i + 1, x[0]] for i, x in enumerate(r)])
add("D24_missing_column", "B3", "NONEQUIV", "R7", "prediction omits a requested column", c, r, ["name"],
    [[x[0]] for x in r])

# D25 cross-column value shuffle (row affiliation broken) -----------------------------------------------------------
add("D25_row_affiliation", "B3", "NONEQUIV", "R7", "stock values shuffled across names (same column multisets)", c,
    r, c, [[r[0][0], r[1][1]], [r[1][0], r[2][1]], [r[2][0], r[0][1]]])
q, c, r = base("B5")
add("D25_row_affiliation", "B5", "NONEQUIV", "R7", "vendor values swapped between two rows", c, r, c,
    [[r[0][0], r[0][1], r[0][2], r[1][3]], [r[1][0], r[1][1], r[1][2], r[0][3]], r[2]])
add("D25_same_valueset_per_row", None, "NONEQUIV", "R7",
    "within-row values swapped across columns: (a=1,b=2) vs (a=2,b=1)", ["a", "b"], [[1, 2]], ["a", "b"], [[2, 1]])

# D26 bool vs int ----------------------------------------------------------------------------------------------------
add("D26_bool_vs_int", None, "NONEQUIV", "R10", "true vs 1", ["flag"], [[True]], ["flag"], [[1]])
add("D26_bool_vs_int", None, "NONEQUIV", "R10", "false vs 0", ["flag"], [[False]], ["flag"], [[0]])

# D27 date-like strings --------------------------------------------------------------------------------------------
add("D27_date_string", None, "EQUIV", "R1", "identical ISO date strings", ["d"], [["2013-07-31"]], ["d"],
    [["2013-07-31"]])
add("D27_date_string", None, "NONEQUIV", "R10", "date vs datetime string", ["d"], [["2013-07-31"]], ["d"],
    [["2013-07-31T00:00:00"]])

# D28 large cardinality permutation (exercises >3-column permutation search paths) ---------------------------------
q, c, r = base("B5")
rows = [[f"P{i:02d}", i, round(i * 1.5, 2), "Acme" if i % 2 else "Bexa"] for i in range(12)]
add("D28_wide_permuted", "B5", "EQUIV", "R3", "12 rows x 4 cols, columns and rows permuted", c, rows,
    [c[3], c[0], c[2], c[1]], [[x[3], x[0], x[2], x[1]] for x in rows[::-1]])
add("D28_wide_permuted", "B5", "NONEQUIV", "R7", "12 rows x 4 cols, one cell changed", c, rows, c,
    rows[:-1] + [[rows[-1][0], rows[-1][1], rows[-1][2], "Zeta"]])


def main():
    out = os.path.join(HERE, "s1_cases.jsonl")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for case in CASES:
            f.write(json.dumps(case, ensure_ascii=False, sort_keys=False) + "\n")
    sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
    me = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()
    from collections import Counter
    manifest = {
        "suite_id": SUITE_ID,
        "n_cases": len(CASES),
        "expected_counts": dict(Counter(c["expected"] for c in CASES)),
        "dimensions": dict(sorted(Counter(c["dimension"].split("_", 1)[0] for c in CASES).items())),
        "s1_cases_sha256": sha,
        "builder_sha256": me,
        "status": "FROZEN BEFORE ANY SCORER RUN",
    }
    with open(os.path.join(HERE, "S1_MANIFEST.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
