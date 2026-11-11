# Changelog

## 1.3.1 — 2026-11-11
No frozen code, data, verdict, prediction or expected output of 1.3.0 changed. Additions:
- `studies/model_output_case_study/posthoc_semicolon_sensitivity/`: the post hoc semicolon-admission sensitivity run
  quoted in paper Section VII (per-unit verdict table, expected statistics, driver, and a network-free check of the
  quoted numbers). Post hoc; not part of the frozen protocol.
- `studies/posthoc_minimal_cases/`: the CypherBench unsortable-list cases of Section IV, the Neo4j trailing-semicolon
  check of Section VII and the integer-versus-float row pre-check cases of Section VI (CypherBench, GQLBench).
- `scripts/corpus_record_checks.py`: network-free check of the corpus record statements of Sections III-B and VI
  against the dataset release.
- `studies/model_output_case_study/README.md`: the Gate40 notebook deviation is listed.

Documentation changes:
- README: version 1.3.1. The quick-start cloned `v1.2.1`, which lacks the model-output study; it now clones `v1.3.1`.
- Paper numbering updated to the submitted manuscript:
  - the model-output study is Fig. 3 (was "Table IX");
  - feature exposure is Table VII (was "Table VIII");
  - the corpus heatmap is Fig. 2 (was "Figure 1").

  Code docstrings and the claim manifest keep their original labels.
- `docs/SCORER_INVENTORY.md`: title no longer says 1.3.0-rc1; "baseline for Fig. 3".
- `docs/result_equivalence_reporting_card.md`: the machine-readable card is in the dataset release (`docs/…yaml`); the previously named `paper/…yaml` path is not part of this repository.
- `CITATION.cff` version 1.3.1 (it said 1.2.2); `VERSION` 1.3.1.
- `provenance/public_file_provenance.csv`: hashes of the edited files updated.

## 1.3.0 — 2026-11-10 (published; tag v1.3.0)
- Adds `studies/model_output_case_study/code/reproduce_case_study.py`, a single driver with four stages:
  - `prepare` rebuilds the frozen question packets from a pinned Mind the Query checkout, byte-identical;
  - `execute` runs Neo4j 5.15.0 Community, with a portable image check;
  - `replay` re-runs the pinned comparators;
  - `table` rebuilds the verdict table byte-for-byte and recomputes Table IX.
- The case-study README states four reproduction levels separately (A–D) and what was tested.
- Adds `frozen/expected_input_hashes.json` and `.gitignore` entries for runtime credentials and work outputs.
- `THIRD_PARTY_NOTICES.md` covers the two models, Mind the Query content and the Neo4j image.

## 1.3.0-rc1 — 2026-11-10 (superseded candidate)
- Adds `studies/model_output_case_study/`: the model-output case study of paper Section VII (two pinned open models, 300 Mind the Query questions):
  - raw predictions;
  - per-unit statuses and verdicts of the baseline and nine comparators;
  - frozen question IDs, graph mappings, policies and runtime files;
  - the scoring, replay and analysis code;
  - a network-free recomputation of Table IX (`code/recompute_case_study.py`).
- Adds `docs/CONFORMANCE_SUITE.md`, `docs/SCORER_INVENTORY.md` and `docs/CORPUS_PROVENANCE_SUMMARY.md`.
- No frozen verdict, study output or previously reported number of v1.2.2 changed.

## 1.2.2 — 2026-11-07
- Adds `graph_conversion/`: the script that converted BIRD's Works-Cycles SQLite database into the Neo4j property graph
  on which the corpus pairs were executed (written by one of the paper's authors and released under Apache-2.0 with the
  author's authorization, as confirmed by the project owner), with an offline fingerprint check, a read-only census of a
  loaded graph, and a script that regenerates the stored SQL and Cypher outputs of the 563 corpus records. Only the
  converter's configuration block differs from the version used originally (no credentials in code); its mapping and
  load logic are unchanged. Verified before release: the rebuilt graph has the same contents as the original graph
  store, label by label and relationship kind by kind; 562 of 563 gold Cypher queries reproduce the stored rows exactly
  and one in a different order; BIRD's official database file is byte-identical to the one used.
- Adds `scripts/cluster_sensitivity.py`, the post-hoc cluster-resampling sensitivity reported in supplement S-G.
- README: the claim manifest is described as covering the scorer-audit claims (other results have their own scripts).
- `environment/requirements.txt` pins `matplotlib==3.11.2`, needed by the Figure 1 renderer (missing in v1.2.0-v1.2.1;
  with it, `scripts/reproduce_exposure.sh` re-renders Figure 1 byte-identically).
  No frozen verdict, study output or previously reported number changed.

## 1.2.1 — 2026-11-07
- Fixes the Mind the Query gold-query runner (`exposure/mtq_results/execute_mtq_gold.py`): v1.2.0 passed a `neo4j.Query`
  object to `tx.run`, which fails for every query; the timeout is now set with `@neo4j.unit_of_work`. The runner script
  uses a local data directory instead of a named Docker volume and a configurable `PYTHON`.
- Adds Mind the Query result-level exposure counts (`exposure/outputs_mtq_result_level/`, same frozen 26-feature detector)
  and a post-hoc sensitivity on the 1,086 native-suite-eligible sources; the raw gold results are not redistributed (hash
  only).
- Adds the intermediate `WITH … ORDER BY` trigger check (`with_orderby_check/`) and the Figure 1 renderer for the six
  in-domain scorers (`figure1/`).
- `scripts/reproduce_exposure.sh` checks result-level counts when the gold results exist and re-renders Figure 1.
  No frozen verdict, v1.2.0 output or previously reported number changed.

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
