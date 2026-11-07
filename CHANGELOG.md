# Changelog

## 1.2.0 — 2026-11-07
- Adds `studies/exposure_and_released_path/`: (1) policy-sensitive feature exposure in CypherTurn and Mind the Query
  gold data (protocol frozen before counting, detector tests, counts, input manifest); (2) a re-run of the GQLBench
  numeric-NULL case through GQLBench's unmodified `cypher_execute` with the real Neo4j driver and `Result.to_df`
  against a live server (protocol, result, query hashes; CypherTurn content is not redistributed); (3) a post-hoc table
  of the 41 six-scorer corpus disagreements by provenance and dimension; (4) a prepared, not executed, script that would
  execute Mind the Query gold queries for result-level exposure.
- Adds `scripts/reproduce_exposure.sh`. No frozen verdict, existing study or reported v1.1.0 number changed.

## 1.1.0 — 2026-11-07
- First public release. Licensed under the Apache License 2.0 (`LICENSE`, `NOTICE`); third-party notices added.
- Includes the controlled fixtures (original and query-consistent corrected versions), frozen scorer verdicts for all
  studies, adapters, analysis code, pre-specified plans, and reproduction scripts.
- Includes the provenance table and per-study SHA-256 hash lists.
- `reproduce.sh --full` accepts the dataset repository root as `CORPUS_PAIRS_DIR`.

## 1.1.0 — 2026-11-07
- `reproduce.sh --quick` now checks the paper-facing analysis: every quantitative claim of the paper and supplement is
  recomputed and compared with `expected_outputs/paper_result_manifest.json`. The v1.0.0 quick check verified the
  original (superseded) controlled suite; it remains, with the v1.0.0 `paper_numbers.py`, as `--legacy-quick`.
- `--full` re-scores the corrected controlled suite (with a regression guard against the superseded values), re-runs the
  second Text2GQL evaluator from explicit inputs (`scripts/text2gql_reference.py`) and rebuilds the model-level table
  from released unit IDs (`scripts/model_level_from_ids.py`). No frozen file or reported number changed.

## Earlier commits (2026-11-02, unreleased snapshots)
- Private pre-release snapshots of the same studies. They carried an MIT `LICENSE`; from v1.0.0 the project code is
  licensed under Apache-2.0. Use v1.0.0 or later.
