# Policy-sensitive feature exposure (upper bound on opportunities, not disagreement)

| Population | items | results available | key-order mismatches |
|---|---|---|---|
| CypherTurn: all turns | 5927 | 5927 | 0 |
| CypherTurn: split=None | 5927 | 5927 | 0 |
| CypherTurn: distinct (graph, query) | 3187 | 3187 | 0 |
| Mind the Query: all test rows | 1829 | 1689 | 0 |
| Mind the Query: logical=1 | 1316 | 1299 | 0 |
| Mind the Query: logical=1, distinct (graph, query) | 1293 | 1276 | 0 |

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
| R_EMPTY | empty results | 0/5927 (0.0%) | 331/1689 (19.6%) |
| R_MULTI_ROW | row order | 3418/5927 (57.7%) | 1066/1689 (63.1%) |
| R_MULTI_COL | column names; column position | 0/5927 (0.0%) | 1138/1689 (67.4%) |
| R_NULL | NULLs | 0/5927 (0.0%) | 21/1689 (1.2%) |
| R_NUMERIC_NULL_COL | NULLs (GQLBench NaN) | 0/5927 (0.0%) | 3/1689 (0.2%) |
| R_NUMERIC | numeric type | 1663/5927 (28.1%) | 896/1689 (53.0%) |
| R_FLOAT | numeric type | 446/5927 (7.5%) | 654/1689 (38.7%) |
| R_NONINTEGRAL_FLOAT | numeric tolerance | 249/5927 (4.2%) | 566/1689 (33.5%) |
| R_INT_FLOAT_MIXED_COL | numeric type | 0/5927 (0.0%) | 1/1689 (0.1%) |
| R_DUPLICATE_ROWS | duplicates | 0/5927 (0.0%) | 197/1689 (11.7%) |
| R_LIST | collections | 0/5927 (0.0%) | 24/1689 (1.4%) |
| R_MAP | collections / graph objects | 0/5927 (0.0%) | 5/1689 (0.3%) |
