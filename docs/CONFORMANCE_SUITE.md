# Using the controlled fixtures as a comparator conformance suite

The 121 fixtures probe one comparison choice each. They are not exhaustive, and conformance to the declared oracle is not semantic correctness.

- **Data.** `text2cypher-corpus/controlled_cases/corrected/s1_corrected_cases.jsonl` (query-consistent suite; template suite in `original/`). Each record has `case_id`, `dimension`, `ref_query`, `pred_query`, `ref_columns`, `pred_columns`, `reference_result`, `predicted_result`, `expected` (`EQUIV`, `NOT_EQUIV` or intent-dependent) and `rule`.
- **Frozen verdicts and agreement.** `studies/validation_repair/validity_repair/s1_corrected/s1_corrected_results.csv`; property checks (reflexivity, symmetry, totality) are summarised in paper Table IV.
- **Re-score the released scorers.** `./reproduce.sh --full <dataset_dir>` fetches the pinned scorers and re-scores every fixture through the format-only adapters (`studies/adapter_readiness/audit_readiness/code/audit_adapters.py`). It reproduced every frozen verdict in the authors' fresh-clone runs before v1.2.2.
- **Recompute the paper's suite numbers.** `./reproduce_quick.sh <dataset_dir>` (no network) recomputes them from frozen verdicts. Tested for this candidate: 57/58 claims checked, 0 mismatches, 1 needing a native rebuild.
- **Testing another scorer.**
  1. Write an adapter that converts a fixture into the scorer's native input (row dictionaries in column order, both query texts) and returns its native pass/fail.
  2. Follow the adapter contract in `audit_adapters.py`: no sorting, deduplication, rounding, case or whitespace change, casting or renaming.
  3. Treat an exception as no verdict.
  4. Compare the verdicts with the `expected` labels, and check reflexivity (`case_id`s of the identical-result dimension), symmetry (swap sides) and totality (every value type gets a verdict).

  The frozen adapter file is hash-checked, so add a new adapter in a separate module.
