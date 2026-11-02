# Reproducibility

| Level | Command | What it verifies | Needs |
|---|---|---|---|
| R0 | `./reproduce.sh --quick` | Every reported number is recomputed from the frozen verdicts; SHA-256 of every released frozen file | Python only |
| R1 | `./reproduce.sh --full` | The pinned scorers, run through the frozen adapters, reproduce every frozen verdict | GitHub access |
| R2 | `./reproduce.sh --full` with Docker | The native-Cypher cases regenerate from public benchmarks with the frozen rules, and the scorers reproduce the verdicts | GitHub access, Docker |

**Boundaries, stated rather than hidden:**
- **Corpus and model-output pairs:** re-scored only when the evaluation dataset's pairs are supplied
  (`CORPUS_PAIRS_DIR`).
- **CypherTurn rebuilds:** match at verdict level, not byte for byte, because Neo4j load order is nondeterministic.
  Mind the Query rebuilds are byte-identical.
- **Development tests:** some per-study tests need inputs that are not redistributed (CypherTurn-derived case files,
  adapter smoke fixtures). In a fresh copy they fail with a missing-file error. They do not affect R0–R2.

**Identifier normalisation.** Internal directory names and a few internal labels were normalised to neutral names for
publication. The scientific content is unchanged. `provenance/public_file_provenance.csv` lists every file with its
SHA-256 and, where the bytes differ from the frozen original, the original's SHA-256. The per-study `hashes.sha256`
files describe the published bytes.
