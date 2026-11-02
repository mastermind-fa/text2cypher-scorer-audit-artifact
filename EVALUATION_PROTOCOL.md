# Evaluation protocol

## Studies
Case identifiers and file names use the study codes below.

| Code | Study | Units | Where |
|---|---|---:|---|
| S1 | Controlled fixtures (synthetic result pairs, one equivalence dimension each); original and query-consistent corrected versions | 121 | `studies/controlled_suite/`, `studies/validation_repair/validity_repair/s1_corrected/` |
| S3 | Corpus audit: result-equivalent SQL–Cypher pairs (pre-specified test) | 563 | `studies/corpus_audit/` |
| S2 | Model outputs (post hoc, descriptive) | 158 | `studies/corpus_audit/`, `studies/validation_repair/validity_repair/model_level_sensitivity/` |
| S18 | Native Cypher: CypherTurn equivalence-preserving rewrites | 60 | `studies/native_cypherturn_validation/` |
| S20 | Native Cypher: CypherTurn policy stress suite | 62 | `studies/native_cypherturn_stress/` |
| S23 | Native Cypher: Mind the Query cross-benchmark replication (rubric frozen before execution) | 77 | `studies/native_mind_the_query/` |

## Scorers
Seven primary scorers: CypherTurn, CypherBench, GQLBench, the Text2GraphQuery-Driver evaluator, PIPE-Cypher, CypherLens
and CySpider. Two secondary comparators, for context only: the neo4j-labs Jaccard notebook and a project reference
comparator (`studies/reference_comparator/code/`). The Text2GraphQuery repository's standalone reference evaluator is run as
an additional, descriptive comparison (`studies/validation_repair/validity_repair/text2gql/`).

Each scorer is run unchanged at its pinned commit. Adapters only convert data formats and replay frozen results.

## Equivalence dimensions
Column naming and position; row order and its trigger; duplicates (bag vs set); integer vs float; float tolerance and
rounding; NULL materialisation; lists; query-text parsing.

## Pre-specified analysis
The corpus test is pre-specified: for each pair of scorers, a one-sided Wilson lower bound on the disagreement rate,
Bonferroni-adjusted over 21 pairs (z = 2.8227), compared with 2%. Native-Cypher studies use rules, oracles and (for
Mind the Query) a replication rubric frozen before execution. Analyses labelled post hoc are descriptive.

## Frozen inputs and outputs
Each study freezes its inputs, scores once, and records SHA-256 hashes before analysis.
