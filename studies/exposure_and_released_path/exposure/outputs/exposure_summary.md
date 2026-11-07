# Policy-sensitive feature exposure (upper bound on opportunities, not disagreement)

| Population | items | results available | key-order mismatches |
|---|---|---|---|
| CypherTurn: all turns | 5927 | 5927 | 0 |
| CypherTurn: split=None | 5927 | 5927 | 0 |
| CypherTurn: distinct (graph, query) | 3187 | 3187 | 0 |
| Mind the Query: all test rows | 1829 | 0 | 0 |
| Mind the Query: logical=1 | 1316 | 0 | 0 |
| Mind the Query: logical=1, distinct (graph, query) | 1293 | 0 | 0 |

| Feature | Dimension | CypherTurn | Mind the Query |
|---|---|---|---|
| Q_ORDER_TRIGGER | row order; query-text dependence | 3365/5927 (56.8%) | 115/1829 (6.3%) |
| Q_FINAL_ORDER_BY | row order | 0/5927 (0.0%) | 75/1823 (4.1%) |
| Q_ORDER_BY_NO_LIMIT | row order | 0/5927 (0.0%) | 50/1823 (2.7%) |
| Q_LIMIT | row order (top-k ties) | 0/5927 (0.0%) | 26/1823 (1.4%) |
| Q_RETURN_DISTINCT | duplicates | 4264/5927 (71.9%) | 76/1823 (4.2%) |
| Q_AGGREGATE | numeric type | 1663/5927 (28.1%) | 483/1823 (26.5%) |
| Q_FLOAT_EXPR | numeric tolerance | 446/5927 (7.5%) | 479/1823 (26.3%) |
| Q_MULTI_ITEM | column names; column position | 0/5927 (0.0%) | 1479/1823 (81.1%) |
| Q_UNALIASED_ITEM | column names | 0/5927 (0.0%) | 895/1823 (49.1%) |
| Q_COLLECTION_EXPR | collections | 0/5927 (0.0%) | 36/1823 (2.0%) |
| Q_OPTIONAL_MATCH | NULLs | 0/5927 (0.0%) | 79/1829 (4.3%) |
| Q_UNION | query-text dependence | 0/5927 (0.0%) | 0/1829 (0.0%) |
| Q_GRAPH_VALUE_ITEM | graph-valued results | 0/5927 (0.0%) | 10/1823 (0.5%) |
| Q_UNPARSED | parser coverage | 0/5927 (0.0%) | 6/1829 (0.3%) |
| R_EMPTY | empty results | 0/5927 (0.0%) | not available |
| R_MULTI_ROW | row order | 3418/5927 (57.7%) | not available |
| R_MULTI_COL | column names; column position | 0/5927 (0.0%) | not available |
| R_NULL | NULLs | 0/5927 (0.0%) | not available |
| R_NUMERIC_NULL_COL | NULLs (GQLBench NaN) | 0/5927 (0.0%) | not available |
| R_NUMERIC | numeric type | 1663/5927 (28.1%) | not available |
| R_FLOAT | numeric type | 446/5927 (7.5%) | not available |
| R_NONINTEGRAL_FLOAT | numeric tolerance | 249/5927 (4.2%) | not available |
| R_INT_FLOAT_MIXED_COL | numeric type | 0/5927 (0.0%) | not available |
| R_DUPLICATE_ROWS | duplicates | 0/5927 (0.0%) | not available |
| R_LIST | collections | 0/5927 (0.0%) | not available |
| R_MAP | collections / graph objects | 0/5927 (0.0%) | not available |
