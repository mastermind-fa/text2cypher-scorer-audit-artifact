# the validation repair validity repair: plan (frozen before any the validation repair scoring)

**Status: POST-REVIEW VALIDITY REPAIR.** This is not part of the original confirmatory design (S12 protocol, S14 freeze). It responds to two evaluator-characterisation defects found in the the pre-release review adversarial review (`the internal issue register (not released)`, I02 and I03).
- Historical frozen outputs are not modified.
- New outputs live only under `studies/validation_repair/validity_repair/`.
- Input hashes: `input_hashes.sha256` in this directory.
- Written 2026-11-01, before any the validation repair run.

**Prior knowledge (disclosed).** The planner has seen:
- all frozen S1/S2/S3/S18/S20/S23 verdicts;
- the the pre-release review finding that 32/121 fixtures have alias sets inconsistent with their result columns;
- the source of `ea_cypher.py` and `impl/evaluation/metrics.py`.

No the validation repair scorer output exists at the time of writing.

## Repair A: query-consistent controlled suite (S1-corrected)

**A1. Affected set (mechanical definition).** A fixture is corrected if either condition holds:
- **(i) alias inconsistency:** on the reference or candidate side, the set of aliases named by the `RETURN` clause differs from the set of result column names (`ref_columns` / `pred_columns`);
- **(ii) identical text:** after any correction under (i), or originally, the reference and candidate query texts are identical. This is the S1 erratum class; replay by query text cannot represent such pairs.

Expected from the the pre-release review analysis: 32 fixtures under (i), plus S1-103…106 under (ii) only, for 36 in total. The builder computes the set; any deviation from 36 is reported, not tuned.

**A2. Correction rules (applied by `code/build_s1_corrected.py`; no manual edits).**
1. Rewrite only the `RETURN` item list. Keep the `MATCH` clause and the tail (`ORDER BY`, `SKIP`, `LIMIT`) unchanged, apart from consistent variable renaming in rule 4.
2. For each result column `c`, in result-column order:
   - **(a)** if `c` is an expression key (contains `.` or `(`), emit `c` without an alias;
   - **(b)** else, if an original item has alias `c`, reuse that item;
   - **(c)** else, if `c` ends in `_alias` and an original item has alias `c[:-6]`, emit that item's expression `AS c`;
   - **(d)** else, if an original item exists at the same position, emit its expression `AS c`; if that expression is a bare variable, emit `<var>.c AS c`;
   - **(e)** else emit `<var>.c AS c`, where `<var>` is the first node variable bound in `MATCH`.
3. Reference and candidate results, columns, `expected`, `rule`, `dimension` and `base` are copied unchanged. Only `ref_query` / `pred_query` change, plus a `correction` record.
4. **Expression keys.** If an expression key names a variable that the side's `MATCH` does not bind, rename that side's bound variable to the one named in the key, throughout that side's text. Example: candidate `MATCH (q:Product)` with key `p.name` becomes `MATCH (p:Product)`.
5. **Identical texts.** If the two texts are identical after rules 1–4, rename the candidate's first bound variable (`x`→`y`, `p`→`q`, `q`→`r`) throughout the candidate text.
6. **Validation (the builder fails on any violation):**
   - both sides' alias sets equal their column sets;
   - `ORDER BY` presence is unchanged on each side;
   - the two texts differ;
   - results, columns and labels are byte-identical to the original JSON values;
   - unaffected fixtures are byte-identical records.

**A3. Scoring.**
- **What runs:** all 121 records of `s1_corrected_cases.jsonl` through the **frozen** runner v1.1 and **frozen** adapters (hash-verified by the runner), for all 7 primary and 2 secondary scorers, once per case.
- **Determinism control:** the 85 unaffected fixtures are part of the run. Their verdicts must equal the frozen `s1_results.csv`. Any difference is reported as an anomaly and is not explained away.

**A4. Comparison (descriptive).**
- Per scorer: the number of fixtures whose verdict changed (original → corrected), listed by fixture and dimension.
- Oracle agreement on the 106 labelled fixtures: original vs corrected.
- No hypothesis tests; the fixtures are designed mechanism probes.

**A5. CypherLens reassessment rule.** A CypherLens policy statement on a dimension may appear in the paper only if corrected-S1 behaviour and native evidence (S18/S20/S23) agree. Where they differ by input shape or domain, the paper states the conditional behaviour. Dimensions: column names, alias-only changes, numeric type, float tolerance, row order, duplicates, column order.

## Repair B: Text2GQL evaluator paths

**B1. Lineage.** Source reading at pinned commit `ab296fab`. Facts and inferences are recorded separately in `text2gql/evaluator_lineage.md`.

**B2. Running `reference/ea_cypher.py`.**
- **Code:** the method `ExecutionEvaluator.compare_results` is loaded verbatim from the git blob (`ast` source segment, same technique as the frozen adapters). It is not edited. Database access (`evaluate`) is not used: rows are supplied as the frozen result rows.
- **Input form:** each row is a dict in column order, matching `session.run(q).data()`.
- **Verdict:** 1 if `compare_results(gold_rows, pred_rows)` is true, else 0. An exception is recorded as `ERROR:<class>`.
- **Gold-error / timeout paths (−1 / 0):** not reachable with frozen rows, and not simulated.

**B3. Cases.** Every set whose frozen result rows are available locally:
- S1 original (121) and S1-corrected (121). `ea_cypher` ignores query text, so both should give identical verdicts; this is a check;
- S18 (60), S20 (62), S23 (77);
- S2 (158) and S3 (563), using the conditional pairs.

**B4. Comparison.**
- Per case: `ea_cypher` verdict vs the frozen Text2GQL-driver (`metrics.py`) verdict. Disagreements are listed by class or dimension.
- Per class (S20/S23): re-derive each class's split with `ea_cypher` in place of the audited path.
- Statement of interest: is equivalence policy path-specific within one released repository? This is supported only if verdicts differ on at least one class.

## Provenance sensitivity
Post hoc, descriptive. Already computed in the pre-release review from frozen verdicts (20/99 vs 21/464; BIRD-derived 1/15 pairs at the S12 criterion). This session reports it unchanged.

## Model-level sensitivity
Separate plan: `../model_level_sensitivity/PLAN.md`. It runs only after Repairs A and B.

## Outputs
- `s1_corrected/`: `s1_corrected_cases.jsonl`, `correction_manifest.csv`, `results/<scorer>.jsonl`, `comparison.csv`, `summary.json`.
- `text2gql/`: `evaluator_lineage.md`, `ea_cypher_verdicts.csv`, `ea_cypher_summary.json`.
- `hashes.sha256` for all outputs.
