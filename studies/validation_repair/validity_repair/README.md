# the validation repair: post-review validity repair (separate reproduction layer)

This layer was added after an adversarial review. It does **not** modify any earlier frozen output. The original controlled suite (`studies/controlled_suite/audit/s1/`) and its verdicts (`studies/corpus_audit/audit_final/frozen/…/s1_results.csv`) are preserved unchanged and remain the historical record.

| Item | What it is | Rerun |
|---|---|---|
| `preregistration/` | Plan and input hashes, written before any the validation repair scoring | — |
| `s1_corrected/` | **Query-consistent controlled suite** (paper-facing), its correction manifest, and verdicts of all 9 scorers. The 85 unaffected fixtures are a determinism control; they reproduce every frozen verdict. | `scripts/full_rescore.py s1_corrected` (needs fetched scorers; compares every verdict and the table with the frozen files). The original `code/` scripts are kept as the frozen record; `compare_s1.py` refers to a research-tree path and is not the release rerun path. |
| `text2gql/` | Lineage of the two audited evaluators of the Text2GQL repository (`impl/evaluation/metrics.py` and `contrib/standalone_text2graph_scripts/reference/ea_cypher.py`), and verdicts of the second one, loaded verbatim on frozen rows | `scripts/text2gql_reference.py` (needs the Text2GQL checkout at `ab296fab` from `third_party/fetch_scorers.sh`; corpus and model-output pairs from the dataset repository; native cases after `full_native.sh`). It loads the frozen `code/run_ea_cypher.py` functions verbatim; that script itself refers to research-tree paths and is kept as the frozen record. |
| `model_level_sensitivity/` | **Post-hoc** model-level EX per scorer (2 models × 138 questions) | `scripts/model_level_from_ids.py <dataset>/model_outputs/s2_not_scored_units.json` rebuilds the table from released unit IDs and checks it byte for byte against the frozen files. The frozen `code/model_level.py` needs the withheld raw predictions. |

**Why this exists.**
- **Template query texts.** In the original suite, 32 fixtures had `RETURN` aliases that did not name their result columns, and 9 had identical reference and candidate texts. This invalidated CypherLens verdicts (which parse aliases from the text) and replay verdicts on those fixtures.
- **Two Text2GQL evaluators.** The Text2GQL repository releases two evaluators with different semantics.

See `internal project records (not released)` in the research repository.
