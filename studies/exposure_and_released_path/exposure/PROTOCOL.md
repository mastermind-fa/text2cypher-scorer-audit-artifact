# S49 — Policy-sensitive feature exposure in public Text-to-Cypher gold data (protocol)

Frozen 2026-11-07 before any feature was counted. Only record schemas (field names, one example record) were inspected.

## Question
How often do the gold queries and gold results of real public Text-to-Cypher benchmarks contain features that can
activate the result-equivalence policy differences documented in the paper (Table II, Table VI dimensions)?

## What this is not
Exposure means the feature is present, so a policy difference *could* change a verdict for some candidate. It is not a
disagreement rate, a flip rate, a population prevalence estimate or a ranking effect. Each percentage is an upper bound on
opportunities for one policy dimension to matter on that benchmark, under that benchmark's own gold data. Features are
not summed or unioned into a headline "exposed" share, because some features (for example a multi-row result) are
present almost by construction.

## Inputs (read-only, local, pinned)
| Benchmark | Source | Unit | Query-level | Result-level |
|---|---|---|---|---|
| CypherTurn | `external/cypherturn/data/scenarios/*_sessions.json` @ `9d9528e1` (7 files; hashes in `source_manifest.json` of S20) | one turn = one scored item | `gold_cypher` | `gold_answer` (released gold rows, JSON) |
| Mind the Query | `external/mind_the_query/Train_Test_Splits/Manual/*/test/*.json` @ `ec4054a1` | one test row | `Cypher` | NOT AVAILABLE: no gold results are released; producing them needs the five dumps loaded into Neo4j (an approval-bound execution). Reported as not run unless the owner approves. |

CypherBench and CySpider gold data are not local (only scorer code is). They are out of scope for this session: adding
them would mean downloading and, for results, deploying their graphs, which does not change a decision here.

Reported populations:
- CypherTurn: all turns with a non-empty `gold_cypher` across all released sessions (primary); breakdown by `split`;
  secondary: distinct (graph, query text).
- Mind the Query: all manual test-split rows (primary); secondary: rows with `logical [0/1]` = "1"; secondary:
  distinct (graph, query text) among those.

## Detection rules (frozen)
Keyword tests run on the query with string literals and backtick names masked (`s23_parse._mask`, reused unchanged).
Final-`RETURN` features use the project's frozen `s23_parse.split_query` (s23-parse-v1); a query it cannot parse (UNION,
CALL, several RETURN keywords, unbalanced brackets) is counted under `Q_UNPARSED`, and its RETURN-item features are
reported as not determined (the denominator for those features excludes it and is printed).

| ID | Policy dimension (Table II) | Rule |
|---|---|---|
| Q_ORDER_TRIGGER | row order; query-text dependence | `"order by" in query.lower()` — the raw substring test CypherBench, GQLBench and the Text2GQL driver apply (strings NOT masked, as in the scorers) |
| Q_FINAL_ORDER_BY | row order | parsed final RETURN has an ORDER BY |
| Q_ORDER_BY_NO_LIMIT | row order | Q_FINAL_ORDER_BY and no LIMIT in the final tail |
| Q_LIMIT | row order (top-k ties) | final tail has LIMIT |
| Q_RETURN_DISTINCT | duplicates | final RETURN DISTINCT |
| Q_AGGREGATE | numeric type | a final RETURN item calls count/sum/avg/min/max/stdev/stdevp/percentilecont/percentiledisc (`\bname\s*\(`) |
| Q_FLOAT_EXPR | numeric tolerance | a final RETURN item calls avg/stdev/stdevp/percentilecont/percentiledisc/tofloat/round, or contains `/` (masked) |
| Q_MULTI_ITEM | column names (PIPE ≥2 rule); column position | final RETURN has ≥ 2 items |
| Q_UNALIASED_ITEM | column names (expression-derived keys; CypherLens alias parsing) | at least one final RETURN item has no `AS` alias (`s23_parse.item_alias`) |
| Q_COLLECTION_EXPR | collections | a final RETURN item contains `[` or `{` (masked) or calls collect/keys/labels/nodes/relationships/range/split/tail/reverse |
| Q_OPTIONAL_MATCH | NULLs | `OPTIONAL MATCH` anywhere (masked) |
| Q_UNION | query-text dependence / parser coverage | `UNION` anywhere (masked) |
| Q_GRAPH_VALUE_ITEM | graph-valued results (untested by the paper) | a final RETURN item is a bare identifier that is bound in a pattern as a node `(x`, relationship `[x` or path `x =` |
| Q_UNPARSED | parser coverage | `split_query` returns None |
| R_EMPTY | errors and empty results | 0 rows |
| R_MULTI_ROW | row order (order can matter only with ≥ 2 rows) | ≥ 2 rows |
| R_MULTI_COL | column names (PIPE ≥2 rule); column position | ≥ 2 columns |
| R_NULL | NULLs | any cell is null |
| R_NUMERIC_NULL_COL | NULLs (GQLBench NaN materialisation) | some column has ≥ 1 null and all its non-null cells are int/float (not bool), at least one non-null |
| R_NUMERIC | numeric type | any int/float cell (not bool) |
| R_FLOAT | numeric type | any float cell |
| R_NONINTEGRAL_FLOAT | numeric tolerance / rounding | any float cell with a non-zero fractional part |
| R_INT_FLOAT_MIXED_COL | numeric type | some column holds both int and float cells |
| R_DUPLICATE_ROWS | duplicates | some row (canonical JSON, column order kept) occurs ≥ 2 times |
| R_LIST | collections | any list cell |
| R_MAP | collections / graph objects | any JSON-object cell (maps and serialised graph objects are indistinguishable in JSON) |

Excluded in advance, with reason: ties under ORDER BY (needs the sort key values, which the result does not always
contain); node/relationship/path *result* values (not distinguishable from maps in JSON); temporal values (JSON strings).

Column order for CypherTurn results is the key order of each `gold_answer` row object; a result's columns are the keys
of its first row (all rows are checked to share keys; a mismatch is reported, not repaired).

## Correction rule
Once counts exist, no feature is added or removed. If a detection bug is found, the rule fix is recorded below with the
reason, and ALL features are recomputed.

## Outputs
`outputs/exposure_counts.csv`, `outputs/exposure_counts.json`, `outputs/exposure_summary.md`, `outputs/input_manifest.json`
(SHA-256 of every input file and of the code), produced by `exposure.py` with no network and no database.

## Corrections log
(none yet)
