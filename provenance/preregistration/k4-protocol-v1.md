# PROTOCOL k4-protocol-v1 (pre-registered; NOT yet run)

**P1. Research questions.**
- **RQ1:** On identical result pairs, how often do released Text-to-Cypher EX scorers disagree?
- **RQ2:** Which implementation choices (dimensions) cause the disagreements, and how often does each scorer deviate from a by-construction oracle?

**P2. Scorers.**
- Primary set: the seven in §7 (#1–#5, #6b, #7b) at the pinned commits / SHA-256 in `external/EXTERNAL_PINS.json`.
- Secondary: neo4j-labs `df_sim_pair == 1.0`, and pc-v1.1 (reference, not ground truth).
- No LLM judge, API or optional LLM component anywhere.

**P3. Adapter contract.**
- Adapters only translate a frozen result pair (reference rows, candidate rows, reference query text, candidate query text) into the scorer's input, invoke the unmodified scorer function, and capture its verdict (0 / 1 or bool → {0,1}).
- Uncaught exceptions are recorded as `ERROR` with the exception class.
- Adapters must not alter or catch inside scorer logic.
- **Determinism:** `random.seed(42)` immediately before each call to scorers #2 and #3. Seed sensitivity: seeds 0–4 on every unit with more than 3 columns; differing units are reported.
- **Adapter fidelity tests (before S1 runs):**
  - **T1:** the import gate (all six import with stubs only for `nebulagraph_python` / `evaluate`).
  - **T2:** a hand-written smoke set disjoint from S1 (5 pairs per scorer). Expected verdicts are derived from the code reading in §6–§7 and written before running. Any mismatch is investigated as an adapter bug, never fixed by changing S1 or the expectations retroactively; the outcome is logged.
  - **T3:** for GQLBench, the `to_df` emulation is checked against the installed `neo4j` 5.26.0 `Result.to_df` source.
- Adapters + tests are frozen (hash-recorded) **before** S1 runs.

**P4. Representation.**
- All pairs are JSON-level Python values (`int`, `float`, `str`, `bool`, `None`, `list`, `dict`) exactly as decoded from the frozen files.
- Neo4j-native objects (Node / Relationship / Path / neo4j.time types) are **out of scope** because the frozen executions are already serialised.
- Stated limitation: graph-object handling is assessed only from code reading (§6–§7), not measured.

**P5. S1 — metamorphic oracle suite `k4-s1-v1`.**
- Built by `experiments/session12/k4/s1/build_s1.py` (SHA-256 `970089fd…`).
- `s1_cases.jsonl`: 121 cases (SHA-256 `80d0fd3fa181470fb5d59c0fbeea9cf748e1cd2bcc3ade61e4387118a17d5b47`); manifest `S1_MANIFEST.json`.
- 28 dimensions, D01–D28: identical; alias renamed; unaliased Cypher expression keys; column order; row order (unordered / gold-ordered / prediction-ordered / both); duplicates; extra / missing row; int vs float; float tolerance (tiny / material); number vs string; NULL vs '' / 0 / 'None'; NULL row permutation; empty results; zero aggregates; all-NULL; string case / whitespace; list values incl. collect order; map values; tied top-k; extra / missing column; row-affiliation shuffles; bool vs int; date strings; wide 12×4 permutations.
- Counts: EQUIV 57 / NONEQUIV 49 / INTENT_DEPENDENT 15.
- **Frozen before any scorer run.** Any change requires a new version (`k4-s1-v2`) created BEFORE any scorer has seen S1, with the reason logged.
- **Oracle rules** (canonical value semantics):
  - **R1:** identical ⇒ EQUIV.
  - **R2:** column names / aliases are presentation ⇒ ignored.
  - **R3:** column / key order is presentation ⇒ ignored, but row affiliation must be preserved.
  - **R4:** row order is irrelevant unless the *reference* query orders.
  - **R5:** if the reference orders, order is part of the answer; ties at or inside the LIMIT boundary ⇒ INTENT_DEPENDENT.
  - **R6:** duplicate multiplicity (bag vs set) and `collect()` element order ⇒ INTENT_DEPENDENT.
  - **R7:** added, removed or re-affiliated rows / values / columns ⇒ NONEQUIV.
  - **R8:** numerically equal int / float ⇒ EQUIV.
  - **R9:** floats equal within relative 1e-9 ⇒ EQUIV; a larger difference ⇒ NONEQUIV.
  - **R10:** type-distinct values (number vs string, bool vs int) and string case / whitespace ⇒ NONEQUIV.
  - **R11:** NULL differs from '', 0 and 'None'.
  - **R12:** both empty ⇒ EQUIV (value-identical, flagged vacuous).
  - **R13:** extra correct projected columns ⇒ INTENT_DEPENDENT.
- The oracle is a *declared* reference semantics, not a claim of the one true semantics. Each scorer is reported against it per rule.

**P6. S2 and S3 (real result pairs; counts verified read-only 2026-10-29).**
- **S3 (PRIMARY real set):**
  - Every record of `database/dataset.json` (SHA-256 prefix `e96196c9b90181d6`) with list-typed `sql_output` and `neo4j_output`: **563** units (9 have an empty side; 1 duplicated question text).
  - Reference = gold-Cypher output + gold Cypher text. Candidate = gold-SQL output + gold SQL text.
  - These are independently authored pairs judged equivalent by the corpus's own validation (`cypher_okay` true on all 563).
  - **Inclusion:** all 563. **No exclusions.** Units with empty sides and the duplicate question are retained and flagged.
- **S2 (secondary):**
  - All G0 units in `primary_execution_s8c.jsonl` with `execution_status = OK`: **158** units (Qwen 82, Phi 76), 111 distinct questions, 0 truncated.
  - Reference = gold-Cypher `neo4j_output` of the mapped dataset record (158 / 158 mapped, none missing, none empty) + gold Cypher text. Candidate = frozen prediction rows + extracted Cypher.
  - **117 / 158 predictions return empty results**, so they are expected to be unanimous 0. Retained, not removed; reported.
  - Non-OK units (118) are listed but not scored (no candidate result).

**P7. Metrics and statistics.**
- **Primary estimand (S3):**
  - For each of the 21 unordered pairs (i, j) of the 7 primary scorers, D_ij = #units with v_i ≠ v_j / #units where both returned a verdict.
  - Report: raw count, denominator, estimate, Wilson 95% CI.
- **Primary hypothesis H1** (refines S11's H2 before any run; see P8): at least one primary pair has a **Bonferroni-adjusted one-sided Wilson lower bound** (α = 0.05 / 21 ⇒ z = 2.8227) **≥ 0.02** on S3.
  - Units are distinct corpus records, so independence is plausible. Bonferroni is valid under the dependence between pairs.
  - **Falsification:** no pair meets this ⇒ report "released scorers do not materially disagree on this corpus" as the negative result. Not a stopping condition.
- **Secondary:**
  1. Unanimity rate (units where all 7 agree), Wilson 95%.
  2. Exact McNemar per pair on S3 (direction: which scorer is more lenient).
  3. S2 pairwise D_ij with question-clustered bootstrap 95% CI (B = 10,000, seed 42, frozen `c3_strata_s8b` style).
  4. S1: per scorer × dimension, conformance on EQUIV (acceptance) and NONEQUIV (rejection) with Wilson 95%; INTENT_DEPENDENT as a behaviour profile only.
  5. Disagreement taxonomy on S3 / S2 by attributing each disagreeing unit to S1 dimensions via a **pre-declared deterministic feature check**:
     - key-name difference;
     - row-order difference;
     - `order by` in which query text;
     - multiplicity difference;
     - int / float / str type difference;
     - float-only numeric difference;
     - NULL presence;
     - list / map cells;
     - empty side.

     Multi-feature units are reported as such.
- **Crash handling:** `ERROR` verdicts are excluded from that pair's primary denominator and counted separately. Sensitivity: `ERROR` → 0.
- **pc-v1.1 and neo4j-labs:** reported alongside, never part of H1.

**P8. Change from Session 11 (documented before any run).**
- S11's H2 pooled S2 ∪ S3 with an unadjusted Wilson bound. Changed to: **S3 only**, with a **Bonferroni-adjusted** bound over the 21 pairs (7 scorers).
- Reasons:
  1. S2 is question-clustered (two models per question), so unit-level Wilson is invalid there.
  2. 117 / 158 S2 units are empty predictions that every scorer marks 0, which mechanically dilutes the rate.
  3. "At least one of 21 pairs" needs multiplicity control.
- The 2% threshold is unchanged.
- **Disclosure:** in S11 the primary agent saw S3 covariates (same column names in 545 / 554 non-empty pairs; a few int / float first-row mismatches; 24 gold outputs with duplicate rows) but **no scorer output**. This may inform expectations; it cannot have tuned any scorer.

**P9. Execution order and stopping rules (next session).**
1. T1 import gate (declared stubs only: `nebulagraph_python`, `evaluate`, `py2neo`, the CypherLens `csv_row`). If fewer than 4 of the 7 primary scorers import and run on the T2 smoke set ⇒ **K4 FAILS → K8**. If 4–6 pass, H1 is re-specified over the passing scorers' pairs **before** S1 runs, with Bonferroni recomputed for the actual number of pairs; this is logged.
2. Adapters + T2 / T3 fidelity tests; freeze the adapter hashes.
3. Run S1 once; hash the outputs.
4. Run S3 and S2 once each; hash the outputs.
5. Statistics script (written and frozen before step 3); tables; one figure.

Stop for K8 if: more than 7 working days in total; a fidelity failure in 2 or more scorers that cannot be fixed without semantic change; or a newly found verified prior audit. A negative H1 is reported, not a stop.

**P10. Resource report.** CPU only; < 1 GB RAM; < 15 MB disk; minutes of runtime; no API key; no network at run time; **$0**.

**P11. Expected outputs.**
- `experiments/session12/k4/` (or the next session dir): `adapters/`, `tests/`, `runs/{s1,s2,s3}/verdicts.jsonl`, `stats/k4_results.json`.
- Three tables: the S1 conformance matrix, the S3 pairwise matrix, and the taxonomy.
- One figure: a pairwise disagreement heat map.
- All TBD — EXPERIMENT REQUIRED.

