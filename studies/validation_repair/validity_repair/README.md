# the validation repair: post-review validity repair (separate reproduction layer)

This layer was added after an adversarial review. It does **not** modify any earlier frozen output. The original controlled suite (`studies/controlled_suite/audit/s1/`) and its verdicts (`studies/corpus_audit/audit_final/frozen/…/s1_results.csv`) are preserved unchanged and remain the historical record.

| Item | What it is | Rerun |
|---|---|---|
| `preregistration/` | Plan and input hashes, written before any the validation repair scoring | — |
| `s1_corrected/` | **Query-consistent controlled suite** (paper-facing), its correction manifest, and verdicts of all 9 scorers. The 85 unaffected fixtures are a determinism control; they reproduce every frozen verdict. | `code/build_s1_corrected.py`, then `code/run_s1_corrected.sh` (needs fetched scorers), then `code/compare_s1.py` |
| `text2gql/` | Lineage of the two evaluators released in the Text2GQL repository, and verdicts of the second one (`reference/ea_cypher.py`), loaded verbatim on frozen rows | `code/run_ea_cypher.py`. Needs the Text2GQL checkout at `ab296fab`. The S2/S3 parts need the corpus pairs (conditional layer). |
| `model_level_sensitivity/` | **Post-hoc** model-level EX per scorer (2 models × 138 questions) | `code/model_level.py`. Needs the frozen S8C prediction files (conditional layer). |

**Why this exists.**
- **Template query texts.** In the original suite, 32 fixtures had `RETURN` aliases that did not name their result columns, and 9 had identical reference and candidate texts. This invalidated CypherLens verdicts (which parse aliases from the text) and replay verdicts on those fixtures.
- **Two Text2GQL evaluators.** The Text2GQL repository releases two evaluators with different semantics.

See `internal project records (not released)` in the research repository.
