# What Counts as Correct? A Cross-Implementation Audit of Execution Accuracy in Text-to-Cypher: research artifact

**Version:** 1.0.0 · **Repository:** https://github.com/mastermind-fa/text2cypher-scorer-audit-artifact · **Dataset:** https://github.com/mastermind-fa/text2cypher-corpus ·
**Licence:** Apache-2.0, for project-authored code only (see `LICENSE`, `NOTICE` and the Licence section)

## Purpose
This artifact reproduces the experimental results of the paper. The paper runs seven released Text-to-Cypher
execution-accuracy scorers, unchanged at pinned commits, on identical result pairs, and traces every disagreement to the
comparison rule in each scorer's code.

## Contents
| Path | What it holds |
|---|---|
| `reproduce.sh`, `reproduce_quick.sh` | Entry points (quick and full reproduction) |
| `scripts/` | Reproduction scripts: quick check, full re-scoring, native-Cypher rebuild, verdict comparison |
| `studies/` | One directory per study: code, tests, pre-specified plans and frozen results (see `EVALUATION_PROTOCOL.md`) |
| `third_party/` | Pinned scorer sources (`scorers.lock`; machine pins in `external/EXTERNAL_PINS.json`), fetch scripts; no third-party code is included |
| `expected_outputs/` | The numbers the quick check must reproduce |
| `environment/` | Pinned Python requirements |
| `docs/` | The Result-Equivalence Reporting Card |
| `provenance/` | SHA-256 of every file, with its pre-normalisation hash where identifiers were normalised |

## Requirements
- Python 3.12; `pip install -r environment/requirements.txt`.
- For full reproduction: `git` and network access to GitHub (to fetch the pinned scorers and the Mind the Query
  benchmark); Docker for the native-Cypher rebuilds (Neo4j 5.15.0, throwaway container).
- CPU only; no GPU, no paid service, no API key.

## Quick reproduction (no network)
```
./reproduce_quick.sh          # same as ./reproduce.sh --quick
```
It recomputes every number reported in the paper from the released frozen verdicts and checks the SHA-256 of every
released frozen file. Measured on an Apple M-series laptop: about one second.

## Full reproduction
```
./reproduce.sh --full                                   # fetch pinned scorers + Mind the Query; re-score; native rebuilds
CORPUS_PAIRS_DIR=/path/to/text2cypher-corpus ./reproduce.sh --full   # also re-score the corpus and model-output pairs
```
- **R1:** re-runs the pinned scorers through the frozen adapters on the controlled fixtures and compares every verdict.
- **R2:** regenerates the native-Cypher cases with the frozen rules and oracle in a throwaway Neo4j, checks input
  hashes, scores once and compares verdicts.
- **Corpus and model-output pairs:** they come from the evaluation dataset. Their re-scoring runs when the pairs are
  supplied; otherwise the boundary is reported, not hidden.

## Expected outputs
`expected_outputs/expected_summary.json` lists the reported numbers. The quick check exits non-zero on any mismatch.
See `REPRODUCIBILITY.md` for what each level verifies.

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
