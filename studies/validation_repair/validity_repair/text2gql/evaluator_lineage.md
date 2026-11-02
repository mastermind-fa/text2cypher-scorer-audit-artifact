# Text2GQL / Text2GraphQuery-Driver: evaluator lineage (the validation repair)

**Repository:** `https://github.com/ldbc/Text2GraphQuery-Driver`. It was formerly `TuGraph-family/text2graphquery-driver`; that URL now returns HTTP 301 to the new one (checked 2026-11-01). The pinned commit is `ab296fab179e806cd3ad2e659e9f5dc61bd1af3e` (2026-09-30, "Add standalone prediction and evaluation references (#3)").

All statements are **SOURCE FACT** (read at the pinned commit) unless labelled INFERENCE.

## Path 1: `impl/evaluation/metrics.py` → `ExecutionAccuracy` (audited in the primary analysis)

| Aspect | Behaviour (source) |
|---|---|
| Call site | `run_pipeline.py:115` constructs `ExecutionAccuracy(self.db_driver)` inside `run_evaluation_phase`. The root README calls `run_pipeline.py` the "Main Entry Point" of the evaluation framework. |
| Intended use | Pipeline metric for every reasoning level (`_evaluate_single_level`). |
| Row normalisation | Values in each row are taken positionally (`r.values()`). Floats are rounded to 9 digits; NaN becomes the string `"NaN"`; Decimal becomes float; bytes become hex; lists become tuples; maps become sorted tuples. |
| Duplicates | **Bag**: `Counter(gold) == Counter(pred)`. |
| Row order | Compared **only if the prediction text contains `order by`** (case-insensitive substring); then the lists must be equal. |
| Column names | Ignored. Columns are positional. |
| Errors | A gold query returning `None` counts the item in the total as incorrect. A failing prediction counts as incorrect. |
| Integer vs float | Python equality: `3 == 3.0` (accepted). |

## Path 2: `contrib/standalone_text2graph_scripts/reference/ea_cypher.py` → `ExecutionEvaluator.compare_results`

| Aspect | Behaviour (source) |
|---|---|
| Call site | Standalone script (`python …/reference/ea_cypher.py --input-path … --database …`). It is not imported by `run_pipeline.py`. Invocation is documented in `contrib/standalone_text2graph_scripts/README.md`. |
| Intended use | The README says the `reference/` files are "retained as reference implementations" and that they "document the evaluation approach used in the experiments", and asks consumers to "adapt them to their own … result-normalization … requirements". |
| Row normalisation | Positional (`row.values()`). Floats are rounded to 9 digits; dates use `isoformat`; lists become tuples; maps become sorted tuples. NaN is **not** mapped specially. |
| Duplicates | **Set**: `{rows} == {rows}`. |
| Row order | **Never compared.** |
| Column names | Ignored. Columns are positional. |
| Errors | A gold error or timeout returns `-1` (item excluded). A prediction error or timeout returns `0`. |

## Which path produced published numbers?
- **FACT.** The repository README names `run_pipeline.py` as the main entry point. The contrib README says the `reference/` scripts "document the evaluation approach used in the experiments".
- **FACT.** The Text2GraphQuery-Bench paper (arXiv 2602.11745; pre-release review) defines execution accuracy without specifying how results are compared.
- **INFERENCE.** We cannot determine from the repository which path produced any published table. Both are released by the same project, and their documentation positions each as an evaluation of record. The paper therefore must not present either as "the Text2GQL policy".

## Measured difference (EXECUTED RESULT; `ea_cypher_verdicts.csv`, `ea_cypher_summary.json`)
Path 2's `compare_results` was loaded verbatim from the pinned blob and run on frozen rows. A harness self-binding bug in the first attempt made every case raise an error. It was fixed, a sanity gate was added, and the outputs of that attempt were discarded.

| Set | n | Path 1 vs Path 2 verdict differences | Where |
|---|---:|---:|---|
| S18 gentle rewrites | 60 | 0 | — |
| S20 CypherTurn stress | 62 | 22 | row order 15/15 (Path 2 accepts), duplicates 7/7 (Path 2 accepts) |
| S23 Mind the Query | 77 | 20 | row order 10/10, duplicates 10/10 (Path 2 accepts) |
| S1 corrected | 121 | 14 | order (D06 1, D07 4), duplicates (D09 7), all-NULL (D19 1), top-k tie (D23 1) |
| S1 original | 121 | 18 | as above, plus 4 identical-text erratum fixtures, where Path 1's replay was affected |
| S2 model outputs | 158 | 0 | — |
| S3 corpus | 563 | 14 | Path 2 accepts 556 vs Path 1 542 |

- Path 2 verdicts are identical on S1 original and S1 corrected: it does not read query text.
- **All other native classes agree** between the two paths: numeric type, float tolerance, NULL, column-name control, column order, reference-side order and list order.

## Consequences (EXECUTED RESULT + INFERENCE)
1. **Row-order class.** Under Path 1, the Text2GQL driver is the only scorer that rejects (on both benchmarks). Under Path 2, all seven primary scorers accept, so the class no longer splits the scorers on either benchmark. The "exact" row-order replication is therefore **path-specific**.
2. **Duplicate class.** Under Path 2, the Text2GQL driver joins PIPE-Cypher and CySpider in accepting. The class still splits the scorers, identically on both benchmarks.
3. **Corpus (descriptive; not pre-specified).** Substituting Path 2 for Path 1, 5 of 15 non-CypherLens scorer pairs still meet the S12 criterion, but the set of pairs changes. Six-scorer non-unanimity is 43/563 (41/563 under Path 1).
4. **Claim supported:** within one released benchmark implementation, two released evaluator paths implement different equivalence semantics (bag vs set; prediction-triggered order check vs none). These differences change verdicts on genuine Cypher pairs.
