# Third-party notices

**No third-party code, benchmark data or graph dumps are included in this repository.** The scripts in `third_party/`
fetch each component from its original repository at a pinned commit into `external/`, which is not tracked. The
adapters run the fetched code unchanged. Where a scorer cannot be imported directly, an adapter extracts the scorer
function from the fetched file at run time; no extracted source is stored here. The GQLBench adapter replaces the
Neo4j driver with a project-written stub that returns the stored rows as a pandas DataFrame.

The licences below were read from each repository's licence file, or from the GitHub API, on 2026-11-02. Each
component is used under its own terms; this repository's Apache License 2.0 does not apply to it.

| Component | Source (pinned commit) | Licence | Use here |
|---|---|---|---|
| CypherTurn | github.com/BarryQ/CypherTurn (`9d9528e16c8f`) | No licence file; README: "This benchmark is released for research purposes." | Scorer; native-Cypher cases rebuilt locally. Only case identifiers and verdicts are published |
| CypherBench | github.com/megagonlabs/cypherbench (`4cc727d29acc`) | Apache-2.0 | Scorer only |
| GQLBench | github.com/qxssadf/GQLBench (`fb9d5a9be3cc`) | No licence file | Scorer only |
| Text2GraphQuery-Driver | github.com/ldbc/Text2GraphQuery-Driver (`ab296fab179e`) | No licence file | Scorer and reference evaluator |
| PIPE-Cypher | github.com/suraj-ranganath/PIPE-Cypher (`0f127208746e`) | MIT, declared in `pyproject.toml`; no licence file | Scorer only |
| CypherLens | github.com/YasmeanMohammadi/cypherLenz (`ce6481941e78`) | No licence file | Scorer only |
| CySpider (SemanticParser4Graph) | github.com/22842219/SemanticParser4Graph (`6cd5eff4aa37`) | Apache-2.0 (`semantic_parser/LICENSE`); no root licence | Scorer only |
| neo4j-labs text2cypher | github.com/neo4j-labs/text2cypher (`a8ed4d9480bc`) | CC0-1.0 | Secondary comparator |
| Mind the Query | github.com/endeavorXx/Mind-the-Query (`ec4054a1b7df`) | Apache-2.0 (repository); the graph dumps derive from neo4j-graph-examples repositories with no licence file | Cross-benchmark cases. Questions are referenced by `unique_id`; dumps and result rows are not redistributed |
| BIRD (`works_cycles`) | bird-bench.github.io | CC BY-SA 4.0 ("our data"; bird-bench.github.io, DAMO-ConvAI `bird/README.md`) | Database needed to re-execute the corpus. Not included here |

Where a repository has no licence file, all rights are reserved by its authors. Those components are therefore
fetched by the user and never redistributed.

Python packages installed from `environment/` (for example pandas and the Neo4j driver) are installed by the user
under their own licences and are not redistributed.

## Model-output case study (added in 1.3.0)
| Component | Source | Licence | Use here |
|---|---|---|---|
| Qwen2.5-Coder-7B-Instruct | huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct @ `c03e6d358207e414f1eca0bb1891e29f1db0e242` | Apache-2.0 (model card) | Generated the released predictions; weights not included |
| Mistral-7B-Instruct-v0.3 | huggingface.co/mistralai/Mistral-7B-Instruct-v0.3 @ `c170c708c41dac9275d15a8fff4eca08d52bab71` | Apache-2.0 (model card) | Generated the released predictions; weights not included |
| Mind the Query questions, schemas, gold queries, dumps | github.com/endeavorXx/Mind-the-Query (`ec4054a1b7df`) | Apache-2.0 (repository); dumps without a licence file | Referenced by `unique_id`; packets are rebuilt locally from a user-fetched checkout; no question text, gold query, dump or result row is redistributed. Model predictions may quote literals from the questions (for example the synthetic e-mail addresses of the entity-resolution example graph) |
| Neo4j 5.15.0 Community Docker image | hub.docker.com `neo4j:5.15.0` | GPLv3 (Neo4j Community, as stated by Neo4j) | Pulled by the user for level D; not included |
