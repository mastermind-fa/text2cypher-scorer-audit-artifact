# Model-level sensitivity: plan (POST HOC; frozen before calculation)

**Status: POST HOC, DESCRIPTIVE.** No new generation or execution. Only frozen the pilot prediction run predictions are used, with frozen the main audit run executions and verdicts. Written 2026-11-01, before any model-level aggregate was computed in the validation repair.

**Prior exposure (disclosed).** The planner has seen:
- per-scorer acceptance counts on the 37-prediction informative subset (S20 and the pre-release review);
- the per-model split of S2 pairs (Qwen3-4B 82, Phi-3.5-mini-instruct 76).

Per-model execution accuracy over the full population was **not** consulted. It may exist in S14 outputs, which are not opened for this purpose.

**Question.** On the already frozen predictions, does the choice of released scorer change aggregate execution accuracy per model, or the relative ordering of the two models?

## Population
- Models: Qwen3-4B (`Qwen/Qwen3-4B`) and Phi-3.5-mini-instruct, both frozen in S8C.
- Questions: the **138 G0 held-out questions**. Both models received the identical set (verified from the extraction files without looking at outcomes). This gives 276 model–question units.
- Units scored in S14 (`s2_results.csv`, 158) carry 7 primary and 2 secondary scorer verdicts.
- Units not scored (`s2_not_scored_units.json`, 118: no extractable query, Cypher error, or other non-OK execution) are **incorrect under every scorer**. This is standard EX: a prediction that does not execute is wrong.

## Outcome
- **Primary.** For model m and scorer s: EX(m, s) = (number of units with verdict `1`) / 138. A scorer exception (`ERROR:*`) counts as incorrect.
- **Sensitivity S1.** A scorer exception is excluded from that scorer's denominator, for that model.
- **Sensitivity S2.** Exclude CypherLens: ranking statements are repeated over the six other primary scorers.

## Reported quantities (all descriptive)
1. A table of EX by model × scorer, for the 7 primary scorers, plus the 2 secondary scorers in a separate block.
2. Per model: the minimum, maximum and range across primary scorers.
3. Per scorer: the gap EX(Qwen) − EX(Phi), and which model ranks higher. Equal EX counts as a **tie**.
4. Ranking change: whether the sign of the gap (or a tie) differs across scorers. Reported for all 7, then without CypherLens.
5. Maximum absolute difference between scorers for the same model, and its scorer pair.
6. Paired descriptive counts per scorer (both correct / only Qwen / only Phi / neither) over the 138 shared questions.

**No significance tests.** The analysis is post hoc, with two models, and the question is whether the ordering differs, not whether a difference is "significant". If every scorer ranks the models the same way, that is reported plainly. If coverage made a comparison invalid, the result would be `NOT ESTIMABLE FROM CURRENT FROZEN OUTPUTS`.

## Interpretation limits (fixed in advance)
- Two small models in one zero-shot configuration on one schema. This is not a leaderboard.
- A ranking flip between two models shows that the scorer choice can change a model-level conclusion **in this setting** only.
