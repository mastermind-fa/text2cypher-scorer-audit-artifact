# Reproducibility

| Level | Command | What it verifies | Needs |
|---|---|---|---|
| R0 | `./reproduce.sh --quick DATASET_DIR` | Every quantitative claim of the paper and supplement (`expected_outputs/paper_result_manifest.json`) is recomputed from frozen verdicts; input SHA-256 checked | Python only |
| R1 | `./reproduce.sh --full DATASET_DIR` | The pinned scorers, run through the frozen adapters, reproduce every frozen verdict of the corrected and original controlled suites, the corpus and the model outputs; the second Text2GQL evaluator reproduces its verdicts; the model-level table is rebuilt from released IDs | GitHub access |
| R2 | `./reproduce.sh --full DATASET_DIR` with Docker | The native-Cypher cases regenerate from public benchmarks with the frozen rules; all scorers and the second Text2GQL evaluator reproduce the verdicts; every manifest claim passes | GitHub access, Docker |

**Boundaries, stated rather than hidden:**
- **Dataset repository (https://github.com/mastermind-fa/text2cypher-corpus):** needed for the corpus and model-output pairs (R1), and for the ID files
  behind the provenance breakdown and the model-level table (R0). Without it, those claims are BOUNDARY, not PASS.
- **One claim needs R2:** the count of multi-column Mind the Query references reads the rebuilt case file.
- **CypherTurn rebuilds:** match at verdict level, not byte for byte, because Neo4j load order is nondeterministic.
  Mind the Query rebuilds are byte-identical.
- **Development tests:** some per-study tests need inputs that are not redistributed (CypherTurn-derived case files,
  adapter smoke fixtures). In a fresh copy they fail with a missing-file error. They do not affect R0–R2.

**Identifier normalisation.** Internal directory names and a few internal labels were normalised to neutral names for
publication. The scientific content is unchanged. `provenance/public_file_provenance.csv` lists every file with its
SHA-256 and, where the bytes differ from the frozen original, the original's SHA-256. The per-study `hashes.sha256`
files describe the published bytes.
