# Works-Cycles graph conversion

Rebuilds the Neo4j property graph on which the 563 corpus pairs were executed, from BIRD's Works-Cycles SQLite database,
and regenerates the stored SQL and Cypher outputs of the corpus records so they can be compared with the released ones.

**Provenance and licence.** `insert_to_neo4j.py` was written by one of the paper's authors, who authorized its release
under the Apache License 2.0 (as confirmed by the project owner; no separate written record is included). It is released
under this repository's `LICENSE`. Only its configuration block differs from the version used to build the experimental
graph: connection settings come from the environment and the SQLite path from the command line. The table-to-label and
foreign-key-to-relationship mapping (`TABLE_PKS`, `FOREIGN_KEYS`) and all load functions are unchanged.

| File | Purpose |
|---|---|
| `insert_to_neo4j.py` | Converter: one node per row (label = table, columns = properties; BLOB columns dropped), one relationship per foreign key with a hand-written type, `MERGE`/`UNWIND` in batches of 500, range indexes on primary keys. |
| `predict_graph_fingerprint.py` | Offline check, no Neo4j: applies the converter's mapping to a SQLite file and compares the predicted counts with the expected fingerprint. |
| `graph_census_check.py` | Read-only check of a loaded graph against the fingerprint (per-label node counts; per `TYPE|From->To` relationship counts). |
| `regenerate_outputs.py` | Re-executes every gold SQL query on the SQLite file and every gold Cypher query on the graph, and compares the rows with the released `sql_output` / `neo4j_output`. |
| `expected_G0_fingerprint.json` | Census of the experimental graph: 64 labels, 719,435 nodes, 84 `TYPE|From->To` kinds, 1,260,831 relationships. |
| `requirements.txt` | Python packages used for the verified run (`neo4j` 5.26.0, `tqdm` 4.70.1). |

## Source data (not redistributed)
BIRD training set, CC BY-SA 4.0 (https://bird-bench.github.io/): `train.zip` → `train/train_databases.zip` →
`train_databases/works_cycles/works_cycles.sqlite`. The file in BIRD's official archive
(downloaded 2026-11-07; archive last modified 2023-07-11) is byte-identical to the one the corpus was built from:
SHA-256 `5a5968b86a2de3cf521294eca7cdc54887830b765e8ca7ab0b103d0f1d7daf1b`, 114,724,864 bytes.

## Recipe
```bash
pip install -r graph_conversion/requirements.txt
python3 graph_conversion/predict_graph_fingerprint.py /path/to/works_cycles.sqlite      # offline; expect MATCHES
docker run -d --rm --name wc-neo4j -p 127.0.0.1:7687:7687 -e NEO4J_AUTH=none neo4j:5.26.28
python3 graph_conversion/insert_to_neo4j.py /path/to/works_cycles.sqlite                 # about 2 minutes
python3 graph_conversion/graph_census_check.py                                          # expect GRAPH CENSUS: MATCHES G0
python3 graph_conversion/regenerate_outputs.py ../text2cypher-corpus/corpus/records_release_candidate.jsonl \
        /path/to/works_cycles.sqlite --neo4j > regeneration_report.json
docker stop wc-neo4j
```
With authentication enabled on the server, set `NEO4J_PASSWORD` (and `NEO4J_URI`, `NEO4J_USERNAME` if needed).

## What was verified (before release, in a clean container)
- **Graph content.** The graph rebuilt with this converter and Neo4j 5.26.28 was compared with a copy of the original
  experimental graph store: every label (64) and every `TYPE|From->To` kind (84) has the same count and the same
  multiset of contents (each node's full property map; each relationship with the full contents of both endpoints),
  and the same range indexes. Node identifiers are not compared (they are internal to Neo4j).
- **Cypher side of the corpus.** On the rebuilt graph, 562 of the 563 gold Cypher queries return exactly the stored
  rows in the stored order, and one returns the same rows in a different order; none differs.
- **SQL side.** With SQLite 3.45.3, 562 of 563 gold SQL queries return exactly the stored rows. The remaining record
  (`WC-008`) returns two columns both named `Name`; its output was stored as one dictionary per row, which keeps only one
  of them, and after the same serialisation it matches exactly. With SQLite 3.53.4, one query without `ORDER BY`
  (`WC-275`) returns the same rows in a different order, as SQL allows.

## Scope
This step regenerates the stored execution results. It does not re-create the frozen scorer verdicts (use
`scripts/full_rescore.py`) or the historical model predictions, which are released as frozen outputs only.
