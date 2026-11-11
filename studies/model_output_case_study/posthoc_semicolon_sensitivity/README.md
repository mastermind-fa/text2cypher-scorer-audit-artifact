# Post hoc semicolon-admission sensitivity (paper Section VII, "Limits")

**Post hoc.** This analysis is not part of the frozen protocol. It was designed and run after the frozen results of the
model-output case study were known (2026-11-11). The frozen analysis in the parent directory remains the primary result.

## What changed
Only the admission gate of the project baseline. The frozen gate (`../code/project_ex.py`, `read_only_query`) rejects
any query containing `;`. Neo4j 5.15.0 executes a query that ends in one semicolon
(`../../posthoc_minimal_cases/neo4j_trailing_semicolon.py`). Here one trailing `;` is ignored when the gate checks a
query; the text sent to Neo4j is unchanged. Predictions, gold queries, graphs, the nine comparators, the adapters and
the statistics code (`code/recompute_case_study.py`, byte-identical to `../code/recompute_case_study.py`) are those of
the frozen study.

## Results quoted in the paper
| Quantity | Frozen run | Post hoc run |
|---|---|---|
| Predictions admitted once one trailing `;` is ignored | — | Qwen 79 (of 80 rejected with a semicolon), Mistral 17 (of 19) |
| Gold queries without a baseline result | 22 | 15 (7 admitted) |
| Evaluable questions (Qwen / Mistral) | 278 / 277 | 285 / 284 |
| Baseline accepted (Qwen / Mistral) | 51 / 28 | 72 / 28 |
| CypherTurn shift, Qwen (points) | −6.8 | −11.9 |
| PIPE-Cypher shift, Qwen | −4.7 | −9.8 |
| Text2GQL driver shift, Qwen | +0.4 | −3.5 (−1.9 without the 84 flagged questions) |
| Paired comparable questions outside the entity-resolution graph | 29 (threshold 30) | 36 |

No Mistral acceptance count changes for any comparator.

## Reproduce
| Level | Command (from the artifact root) | Needs | Status |
|---|---|---|---|
| A | `python3 studies/model_output_case_study/posthoc_semicolon_sensitivity/code/check_paper_numbers.py` and `python3 studies/model_output_case_study/posthoc_semicolon_sensitivity/code/recompute_case_study.py` | Python 3 only | Tested: PASS |
| C–D | `reproduce_case_study.py prepare` (parent study), then `…/posthoc_semicolon_sensitivity/code/semicolon_sensitivity.py execute`, `replay`, `table` | Docker, `neo4j:5.15.0`, network, the pinned scorer environment | Tested from this release's tree on 2026-11-11: `execute` with `--reuse-running` against the four read-only graph containers of the parent study's end-to-end test (600 units, Neo4j 5.15.0 Community), `replay` (nine comparators, 244 scored pairs) and `table` (unit table byte-identical to `verdicts/case_study_units.csv`; statistics match). Provisioning the containers from the dumps was not repeated for this run |

## Contents
- `verdicts/case_study_units.csv`: 600 units of the post hoc run, same columns as `../verdicts/case_study_units.csv`.
- `expected/expected_case_study.json`: acceptances, shifts with both bootstrap intervals, McNemar and ranking inputs.
- `code/semicolon_sensitivity.py`: the driver (gate wrapper plus the released stages).
- `code/check_paper_numbers.py`: checks the numbers above.

Raw result rows are not redistributed (same reason as in the parent study).
