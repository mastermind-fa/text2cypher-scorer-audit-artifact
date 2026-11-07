# S49 — GQLBench released-path verification: RESULT

**Outcome A — confirmed.** Executed 2026-11-07 under `PROTOCOL.md` (committed `16cd528` before execution).

| Run | GQLBench return | Expected | Match |
|---|---|---|---|
| R1 flagship (frozen 29 rows, 12 NULLs in integer `p_opt`, `ORDER BY` in reference) | `(0, 'last res_eq')` | reject | yes |
| R2 same rows, no `ORDER BY` (set path) | `(0, 'last res_eq')` | reject | yes |
| R3 control, NULL→0 | `(True, 'last res_eq')` | accept | yes |
| R4 control, NULL only in the string column | `(True, 'last res_eq')` | accept | yes |
| R5 identical query text | `(1, 'No Error')` (text shortcut) | accept | yes |

The frozen S20 adapter verdict for S20-69098610ca is the same return value, `(0, 'last res_eq')`
(frozen raw GQLBench output of the CypherTurn stress suite).

## Environment (recorded by the script)
Neo4j server 5.26.28 (Docker `neo4j:5.26.28`, throwaway container, no volumes/bind mounts, removed after the run);
neo4j Python driver 5.26.0; pandas 2.3.3; numpy 2.5.3; Python 3.12.15; GQLBench `fb9d5a9b`, `Code/eval/execute_accuracy.py`
unmodified. Deviations exactly as listed in the protocol (Nebula import stub, credentials set as module globals,
`db_name="neo4j"`, rows emitted by a read-only `UNWIND` query instead of the CypherTurn graph).

## Mechanism (measured probe + code)
1. `cypher_execute` calls `driver.execute_query(Query(...), database_=..., result_transformer_=neo4j.Result.to_df)`.
   In driver 5.26.0, `to_df(expand=False)` is `pd.DataFrame(self.values(), columns=self._keys)`.
2. pandas infers the integer-plus-NULL column `p_opt` as `float64`; each NULL becomes `NaN` (probe: dtype `float64`,
   12 NULL cells, Python type `float`, 12 distinct objects on one side).
3. `df.itertuples(index=False)` yields a fresh Python `float('nan')` object per cell; `cypher_value_to_python_value`
   passes floats through unchanged.
4. `execution_accuracy` → `res_eq` → `quick_rej`. With `order_matters=True` it evaluates `s1 == s2` on lists of
   row tuples; otherwise `set(tuple(s1)) == set(tuple(s2))`. Python container equality treats two elements as equal only
   if they are the same object or `==` holds; the two sides' `NaN`s are different objects (`a is b` False) and
   `NaN == NaN` is False, so the tuples differ (probe: `tuple_eq` False). In the set branch, `hash(nan)` is
   object-identity based in Python ≥ 3.10 (probe: different hashes), so the rows never match either.
   `quick_rej` returns False and `res_eq` returns `0` before the permutation search.
5. A string column with NULL stays `object` dtype and keeps `None` (a singleton), so R4 is accepted.
6. If both query texts are identical after `strip()`, the function returns 1 without executing (R5); the rejection
   therefore needs two different texts with identical results, as in the frozen case.

## Claim consequence
The manuscript statement that GQLBench rejects identical results when a numeric column contains NULL is now verified
through GQLBench's own execution path with the real driver, `Result.to_df` and a live Neo4j server, not only through the
replay adapter. Not verified: the CypherTurn graph itself was not loaded (the rows were emitted by `UNWIND`), and no
other driver/pandas versions were tried.
