# What Counts as Correct? A Cross-Implementation Audit of Execution Accuracy in Text-to-Cypher: research artifact

**Version:** 1.2.1 · **Repository:** https://github.com/mastermind-fa/text2cypher-scorer-audit-artifact · **Dataset:** https://github.com/mastermind-fa/text2cypher-corpus ·
**Licence:** Apache-2.0, for project-authored code only (see `LICENSE`, `NOTICE` and the Licence section)

## Purpose
This artifact reproduces the experimental results of the paper. The paper runs seven released Text-to-Cypher
execution-accuracy scorers, unchanged at pinned commits, on identical result pairs, and traces every disagreement to the
comparison rule in each scorer's code.

## Model-output case study (1.3.0)
`studies/model_output_case_study/` holds the model-output case study of paper Section VII (Table IX): predictions of two
pinned open models on 300 Mind the Query questions, per-unit verdicts of the baseline and nine comparators, policies,
runtime files and code. `python3 studies/model_output_case_study/code/recompute_case_study.py` recomputes Table IX
without network access. See its README for provenance stages and disclosed deviations, and `docs/` for the conformance
suite, the scorer inventory and the corpus provenance summary.

## Contents
| Path | What it holds |
|---|---|
| `reproduce.sh`, `reproduce_quick.sh` | Entry points (quick and full reproduction) |
| `scripts/` | Reproduction scripts: paper check, full re-scoring, second Text2GQL evaluator, model-level rebuild, native-Cypher rebuild, verdict comparison |
| `studies/` | One directory per study: code, tests, pre-specified plans and frozen results (see `EVALUATION_PROTOCOL.md`) |
| `third_party/` | Pinned scorer sources (`scorers.lock`; machine pins in `external/EXTERNAL_PINS.json`), fetch scripts; no third-party code is included |
| `expected_outputs/` | `paper_result_manifest.json`: the scorer-audit claims of the paper and supplement, with their inputs' SHA-256 (other results have their own scripts; see the table below) |
| `graph_conversion/` | The script that built the Works-Cycles property graph from BIRD's SQLite database, graph checks, and a script that regenerates the stored SQL and Cypher outputs of the corpus (see `graph_conversion/README.md`) |
| `environment/` | Pinned Python requirements |
| `docs/` | The Result-Equivalence Reporting Card |
| `provenance/` | SHA-256 of every file, with its pre-normalisation hash where identifiers were normalised |

## Requirements
- Python 3.12; `pip install -r environment/requirements.txt`.
- For full reproduction: `git` and network access to GitHub (to fetch the pinned scorers and the Mind the Query
  benchmark); Docker for the native-Cypher rebuilds (Neo4j 5.15.0, throwaway container).
- CPU only; no GPU, no paid service, no API key.

## How to regenerate every reported number
```
git clone --branch v1.2.1 https://github.com/mastermind-fa/text2cypher-scorer-audit-artifact && cd text2cypher-scorer-audit-artifact
git clone --branch v1.0.1 https://github.com/mastermind-fa/text2cypher-corpus ../text2cypher-corpus   # dataset release (ID files, corpus pairs)
python3 -m pip install -r environment/requirements.txt
./reproduce.sh --quick ../text2cypher-corpus                # R0: all paper claims from frozen verdicts (no network)
./reproduce.sh --full  ../text2cypher-corpus                # R0 + R1 + R2: re-score everything (GitHub access, Docker)
```
- **R0 (`--quick`, about one second):** recomputes every quantitative claim of the paper and supplement from the
  released frozen verdicts and compares it with `expected_outputs/paper_result_manifest.json`: the corrected
  (query-consistent) controlled suite, the corpus test, both Text2GQL evaluators, the model-output analyses, the
  model-level table (rebuilt from released unit IDs and compared byte for byte), the provenance breakdown and the
  native-Cypher suites. Without the dataset path, the claims that need its ID files are reported as BOUNDARY and the
  run ends PARTIAL, never PASS.
- **R1 (`--full`):** fetches the pinned scorers and re-runs them through the frozen adapters on the corrected controlled
  suite (paper-facing; a regression guard fails if the superseded original values come back), the original suite
  (kept as a superseded record), the corpus pairs and the model-output pairs; re-runs the second Text2GQL evaluator
  (`reference/ea_cypher.py`) on the same pairs.
- **R2 (`--full`, Docker):** regenerates the native-Cypher cases from CypherTurn and Mind the Query with the frozen rules
  and oracle in a throwaway Neo4j 5.15.0, re-scores them with all scorers and with the second Text2GQL evaluator, and
  finally requires every manifest claim to pass.
- `scripts/reproduce_exposure.sh ../text2cypher-corpus` (after the two fetch scripts in `third_party/`): recounts the
  26 pre-specified policy-sensitive features in CypherTurn and Mind the Query gold data, rebuilds the post-hoc
  provenance-by-dimension table and re-renders Figure 1, comparing each with the released outputs. Mind the Query
  result-level counts (v1.2.1) are checked after `studies/exposure_and_released_path/exposure/mtq_results/run_mtq_gold.sh`
  (Docker, about 5 minutes) has executed its gold queries. The GQLBench live-server check is
  described in `studies/exposure_and_released_path/gqlbench_released_path/PROTOCOL.md` (Docker; read-only queries).
- `./reproduce.sh --legacy-quick` runs the v1.0.0 checks (`quick_check.py`, which verifies the ORIGINAL controlled
  suite that the paper reports only as superseded, and `paper_numbers.py`, ten headline numbers also covered by R0).

## Expected outputs
`expected_outputs/paper_result_manifest.json` lists each claim with its manuscript location, layer, input files and
their SHA-256, and the expected value. `scripts/paper_check.py` exits non-zero on any mismatch.
`expected_outputs/expected_summary.json` belongs to the legacy quick check. See `REPRODUCIBILITY.md`.

## Paper results and where they come from
| Paper result | Released frozen output | Checked by |
|---|---|---|
| Controlled suite, agreement with the declared oracle | `studies/validation_repair/validity_repair/s1_corrected/s1_corrected_results.csv` (template-text suite: `studies/controlled_suite/`) | `scripts/paper_numbers.py`, `scripts/quick_check.py` |
| Equivalence properties and code-level mechanisms | per-case verdicts of all layers; scorer code at the pinned commits | `scripts/full_rescore.py`, `scripts/full_native.sh` |
| Native Cypher: CypherTurn and Mind the Query | `studies/native_cypherturn_stress/…/s20_verdicts.csv`, `studies/native_mind_the_query/…/s23_verdicts.csv` | `scripts/quick_check.py`; rebuild: `scripts/full_native.sh s20 \| s23` |
| Two Text2GQL evaluators: 542 vs 556 of 563, 14 differences | `studies/validation_repair/validity_repair/text2gql/ea_cypher_verdicts.csv` | `scripts/paper_numbers.py` |
| Corpus: per-scorer acceptances, 5/15 in-domain and 11/21 pairs, 41/563 non-unanimous, heatmap figure | `studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final/s3_results.csv`, `s3_pairwise_disagreement.csv` (the full 21-pair table) | `scripts/quick_check.py`, `scripts/paper_numbers.py` |
| Provenance split 20/99 vs 21/464 | `s3_results.csv` with the corpus records (https://github.com/mastermind-fa/text2cypher-corpus) | `CORPUS_DIR=<corpus> scripts/paper_numbers.py` |
| Policy-sensitive feature exposure (Table VIII) | `studies/exposure_and_released_path/exposure/outputs/exposure_counts.csv` | `scripts/reproduce_exposure.sh` |
| Mind the Query result-level exposure (Table VIII, v1.2.1) and post-hoc 1,086-source sensitivity | `studies/exposure_and_released_path/exposure/outputs_mtq_result_level/` | `run_mtq_gold.sh`, then `scripts/reproduce_exposure.sh` |
| Intermediate `WITH … ORDER BY` trigger check (Section V-E) | `studies/exposure_and_released_path/with_orderby_check/result.json` | `check_with_orderby.py` (after `third_party/fetch_scorers.sh`) |
| Figure 1 (six in-domain scorers) | `studies/exposure_and_released_path/figure1/figure1_s3_heatmap.png` | `render_figure1.py` |
| GQLBench numeric-NULL rejection on a live server | `studies/exposure_and_released_path/gqlbench_released_path/RESULT.md`, `results_public.json` | protocol in the same folder |
| Corpus disagreements by provenance and dimension (post hoc) | `studies/exposure_and_released_path/provenance_by_dimension/expected_output.txt` | `scripts/reproduce_exposure.sh <corpus>` |
| Supplement S-G: post-hoc cluster-resampling sensitivity of the corpus pairwise bounds | computed from `s3_results.csv` and the corpus records | `python3 scripts/cluster_sensitivity.py <corpus>` |
| Stored SQL and Cypher outputs of the 563 corpus records (regeneration from BIRD's database) | corpus `records_release_candidate.jsonl` | `graph_conversion/` (Docker, Neo4j 5.26.28) |
| Model outputs and model level | `…/s2_results.csv`, `studies/validation_repair/validity_repair/model_level_sensitivity/model_level_ex.csv` | `scripts/quick_check.py`, `scripts/paper_numbers.py` |

## Pre-specified protocol
The corpus-audit protocol (`k4-protocol-v1`) is in `provenance/preregistration/`, byte-for-byte as committed, with its
commit, tag and hash identifiers and a statement of what can and cannot be verified independently.

## Verifying files
Every file's SHA-256 is in `provenance/public_file_provenance.csv`, and each study has a `hashes.sha256`.
`./reproduce.sh --quick` checks the hashes of all released frozen files before recomputing any number.

## What is project code
Everything in this repository is project-authored (adapters, runners, analysis, reproduction scripts, documentation)
except the licence texts. The audited scorers are fetched from their own repositories at the pinned commits below and
run unchanged; none of their code is stored here.

## Scorer notes
- **Text2GQL:** the benchmark is Text2GraphQuery-Bench (first released as Text2GQL-Bench); its evaluators are in
  `ldbc/Text2GraphQuery-Driver`. We audit two of them: the pipeline evaluator `impl/evaluation/metrics.py`
  (`ExecutionAccuracy`) and the reference script `contrib/standalone_text2graph_scripts/reference/ea_cypher.py`
  (`ExecutionEvaluator.compare_results`, called directly on frozen rows, so its `-1` return for a failing gold query
  never occurs). The frozen validity-repair plan refers to the second file by its short name `reference/ea_cypher.py`.
- **CySpider:** `semantic_parser/metrics/text2cypher/evaluator.py`, function `eval_exec_match`, commit `6cd5eff4`
  (the repository's `evaluator_kaya.py` copy differs only in commented-out debug output).
- **CypherTurn:** two empty results score 1.0. In the model outputs, no empty prediction has an empty gold result.

## Scorer versions
| Scorer | Source | Commit | Licence |
|---|---|---|---|
| cypherturn | https://github.com/BarryQ/CypherTurn | `9d9528e16c8f` | NO LICENSE FILE at commit (licence UNVERIFIED; GitHub API rate-limited) |
| cypherbench | https://github.com/megagonlabs/cypherbench | `4cc727d29acc` | Apache-2.0 (LICENSE file) |
| gqlbench | https://github.com/qxssadf/GQLBench | `fb9d5a9be3cc` | NO LICENSE FILE at commit (licence UNVERIFIED) |
| tugraph_driver | https://github.com/TuGraph-family/text2graphquery-driver | `ab296fab179e` | NO LICENSE FILE at commit (licence UNVERIFIED) |
| pipecypher | https://github.com/suraj-ranganath/PIPE-Cypher | `0f127208746e` | MIT (pyproject.toml) |
| neo4jlabs_text2cypher | https://github.com/neo4j-labs/text2cypher | `a8ed4d9480bc` | CC0-1.0 (LICENSE file) |
| cypherlens | https://github.com/YasmeanMohammadi/cypherLenz | `ce6481941e78` | NO LICENSE FILE at commit (licence UNVERIFIED) |
| cyspider | https://github.com/22842219/SemanticParser4Graph | `6cd5eff4aa37` | Apache-2.0 (semantic_parser/LICENSE) |
| mind_the_query | https://github.com/endeavorXx/Mind-the-Query | `ec4054a1b7df` | Apache-2.0 LICENSE file at commit (repository content); graph dumps derive from neo4j-graph-examples repos with NO licence file (dump licence UNVERIFIED) |

## External dependencies
Third-party scorers and benchmarks are fetched from their original repositories at the pinned commits
(`third_party/README.md`) and are never redistributed here.

## Citation
See `CITATION.cff`. The paper is under review at ICDE 2027.

## Licence
The Apache License 2.0 (`LICENSE`, with `NOTICE`) covers the project-authored code and documentation in this repository only. It does not
cover:
- third-party scorer code, which is fetched from its original repositories at pinned commits under each upstream
  repository's own terms and is never redistributed here (`third_party/`);
- third-party benchmark data (CypherTurn, Mind the Query, BIRD), which is fetched, not included;
- the evaluation dataset, which is released separately under CC BY-SA 4.0.

Third-party components and their licences are listed in `THIRD_PARTY_NOTICES.md`.

Much of the project code was generated or revised with AI assistance under the authors' direction (see the paper's
AI-assistance acknowledgment). The licence grants whatever rights the authors hold in this code; it makes no claim
about the copyright status of individual AI-generated passages.

## Limitations
See `KNOWN_LIMITATIONS.md`.
