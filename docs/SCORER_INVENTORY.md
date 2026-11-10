# Scorer inventory, eligibility and input domains (1.3.0-rc1)

- **Search:** a targeted, **non-systematic** search of papers and repositories (28–29 Oct 2026). No reproducible search log beyond the paper's description exists.
- **Inclusion:** released, deterministic Text-to-Cypher result comparators, runnable without paid services.
- **Exclusion:** no released comparison code (e.g. Mind the Query, LAST-CQ set equality), and LLM judges.

| Implementation | Class | Pin | Licence (as read) | Native input | Domains and coverage notes |
|---|---|---|---|---|---|
| CypherTurn | third-party primary | 9d9528e1 | no licence file | Neo4j query results as dicts; result-key names compared | in-domain on all layers |
| CypherBench | third-party primary | 4cc727d2 | Apache-2.0 | result rows; reads reference text for `order by` | in-domain |
| GQLBench | third-party primary | fb9d5a9b | no licence file | pandas DataFrame via `Result.to_df` | in-domain; NaN behaviour on numeric NULL |
| Text2GQL driver (`ExecutionAccuracy`) | third-party primary | ab296fab | no licence file | positional rows; reads prediction text for `order by` | in-domain |
| Text2GQL reference script (`ea_cypher.py`) | third-party, second evaluator | ab296fab | no licence file | positional row sets | reported alongside the driver |
| PIPE-Cypher | third-party primary | 0f127208 | MIT (pyproject) | answer sets; names required for multi-column rows | in-domain |
| CypherLens (`build_table` + `compute_exact_match`) | third-party primary | ce648194 | no licence file | aliases parsed from the **candidate's Cypher `RETURN`** | **out of domain on the SQL–Cypher corpus** (SQL candidate; its failures there are reported as diagnostic, not as defects); **in domain** on native-Cypher layers and on the model-output case study, where both sides are Cypher (run there through a separately labelled path with the same runner and pins) |
| CySpider | third-party primary | 6cd5eff4 | Apache-2.0 (sub-directory) | positional row sets | raises on list/map values (recorded as no verdict) |
| neo4j-labs Jaccard notebook | third-party secondary | a8ed4d94 | CC0-1.0 | per-row value sets; Jaccard = 1 accepted | context only |
| pc-v1.1 | **project-authored** comparator | project | Apache-2.0 (this repo) | bag of rows, best bijection, numeric tolerance | context only; written by the authors of the declared oracle, so not independent |
| Baseline of the model-output study (`s55-project-ex-v1`) | **project-authored** | `project_ex.py` 58920a41 | Apache-2.0 (this repo) | positional multiset, 1e-9 tolerance, conservative read-only admission | baseline for Table IX only; not an official Mind the Query metric |

Commits and scorer-file SHA-256 values are in `third_party/scorers.lock`. They were verified for this candidate on 2026-11-10: all 8 match.
