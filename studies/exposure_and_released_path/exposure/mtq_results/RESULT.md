# Mind the Query result-level exposure (v1.2.1)

`run_mtq_gold.sh` (Docker; throwaway Neo4j 5.15.0, data directory under `scratch/`, removed on exit) loads the five pinned
Mind the Query dumps one at a time and executes each of the 1,829 manual test-split gold queries once in a read
transaction (60 s timeout, never retried). Set `PYTHON` to an interpreter with the `neo4j` driver (default `python3`).

Result: 1,689 queries returned a result; 140 failed in Neo4j (138 CypherSyntaxError, 1 CypherTypeError,
1 ArithmeticError), mostly SQL-style constructs (`GROUP BY`, `OVER`), `distance()` (replaced by `point.distance` in
Neo4j 5) and aggregation-scoping errors. None of the failures carries the annotators' positive `result` label.
The raw output (`mtq_gold_results.jsonl`) is not redistributed (the graph dumps' licence is unverified); its SHA-256 is in
`mtq_gold_results.sha256`. Two independent executions produced byte-identical output.

The v1.2.0 copy of `execute_mtq_gold.py` passed a `neo4j.Query` object to `tx.run`, which the driver rejects inside
managed transactions (every query failed with `ValueError`); v1.2.1 sets the timeout with `@neo4j.unit_of_work`.
`run_mtq_gold.sh` now bind-mounts a local data directory instead of a named Docker volume.

Counts: `../outputs_mtq_result_level/` (same frozen detector; all query-level rows identical to `../outputs/`).
Post-hoc sensitivity on the 1,086 native-suite-eligible sources: `../outputs_mtq_result_level/sensitivity_s23_eligible.json`.
These are frequencies of features in gold results, not scorer disagreement, score impact or ranking impact.
