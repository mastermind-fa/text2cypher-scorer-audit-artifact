# Minimal cases executed after the frozen runs

Three observations in the paper rest on minimal executions that are not part of any frozen layer.

| Paper location | Script | Observation |
|---|---|---|
| Section IV, CypherBench reflexivity | `cypherbench_unsortable_list.py` (pinned CypherBench through the frozen adapter; no database) | Identical results whose list values cannot be sorted (`[1, null]`, mixed types, maps with a missing property) are rejected when the two query texts differ; with the unsortable list on the reference side only, the scorer raises. Expected output: `expected_cypherbench_unsortable_list.json` |
| Section VI, Mechanisms (corpus pair S3-473) | `row_precheck_int_float.py` (pinned CypherBench and GQLBench through the frozen adapters; no database) | Both accept `21` against `21.0` in a one-column result and reject `(210, 21)` against `(210, 21.0)`: the row pre-check inherited from the Spider test-suite evaluator sorts each row by value string plus type name. Expected output: `expected_row_precheck_int_float.json`. The corpus pair itself is checked by `scripts/corpus_record_checks.py` |
| Section VII, Limits | `neo4j_trailing_semicolon.py` (empty throwaway Neo4j 5.15.0) | A query ending in one semicolon executes; two statements raise a syntax error |

No controlled, native or corpus case contains an unsortable list, so no frozen verdict depends on the first observation. All three scripts were run on 2026-11-11 with the expected results.
