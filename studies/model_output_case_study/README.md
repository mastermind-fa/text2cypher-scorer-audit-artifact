# Model-output case study (paper Section VII, Fig. 3) — release 1.3.1

The paper reports this study as Fig. 3. Releases up to 1.3.0, and the code docstrings, call it "Table IX".

Two pinned open models generated Cypher for 300 Mind the Query test questions. Each prediction was executed against its
gold query on the benchmark's own graphs and scored by a project-defined baseline comparator and by the nine replayed
comparators of the audit. Fig. 3 reports how much each scorer shifts measured accuracy against the baseline.

## Provenance and stages
| Stage | Questions per model | Governed by |
|---|---:|---|
| Gate40 | 40 | Original frozen protocol: a 6/40 per-model viability floor (both passed: Qwen 11/40, Mistral 8/40) |
| Extension | 260 | The same protocol plus post-Gate40 prospective decisions P1–P6 (`policy/FINAL_P1_P6_POLICY_55K.md`, SHA-256 `770d3160…`, approved 2026-11-10 before extension inference; **not pre-registered**) |
| Combined | 300 | Mixed: not wholly prospective |

- **Models:** `Qwen/Qwen2.5-Coder-7B-Instruct@c03e6d358207e414f1eca0bb1891e29f1db0e242` and `mistralai/Mistral-7B-Instruct-v0.3@c170c708c41dac9275d15a8fff4eca08d52bab71`.
- **Generation:** zero-shot from question and schema; greedy decoding, seed 55, NF4 4-bit; at most 4,096 prompt and 256 new tokens. Prompt template SHA-256 `13c431f0…6f6e`; runner `8dbdb196…1bbf`. Run on Kaggle (2× Tesla T4; runtime lock in `runtime/`). Gold queries are never in prompts.
- **Questions:** `frozen/question_ids_*.json` lists question IDs and graphs only; fetch the questions from Mind the Query at commit `ec4054a1` with `third_party/fetch_mind_the_query.sh`.
- **Execution:** read-only Neo4j 5.15.0 Community, one instance per graph, under `policy/GATE40_55F_COMMUNITY_SECURITY_AMENDMENT.md`. Graph identity was checked by node, relationship, label and type counts; the frozen elementId hash is not reproducible across instances.
- **Materiality criterion:** a paired accuracy difference of ≥ 2 points between a scorer and the baseline, fixed in `policy/FROZEN_PROTOCOL.md` before any model output existed, reported with question- and near-cluster bootstrap intervals. It is an effect-size criterion, not a significance test.

## Disclosed deviations
1. The Kaggle notebook that produced the extension differs from the frozen `runtime/session55_ext260_frozen_v1.ipynb` in 3 of 5 code cells:
   - a pinned `bitsandbytes`/`accelerate` install step, whose own record was not preserved;
   - an exactly-2-T4 check;
   - streamed logs.

   Library versions equal the lock, and all prediction-determining inputs were verified. See `runtime/EXECUTED_vs_FROZEN_EXT260_NOTEBOOK.diff`. The owner accepted this before scoring.
2. Denominators for gold queries that do not run (22) and for one unsupported prediction are a convention adopted after scoring. All material/not-material conclusions are unchanged under the three denominator conventions in `code/audit_55m.py`.
3. The baseline admission check rejects any query containing `;`. That removes 80 Qwen and 19 Mistral predictions before comparison. A post hoc run that ignores one trailing `;` is in `posthoc_semicolon_sensitivity/` (release 1.3.1); the frozen analysis here is unchanged.
4. The Neo4j image declares `/logs` as a volume, so Docker created unnamed log volumes. Logs were copied out and are not needed for reproduction.
5. The Gate40 notebook that was executed also differs from the approved one: it adds a pinned dependency-install cell before the runtime check and returned one extra file (`dependency_bootstrap.log`), so the original archive validator stopped at its inventory check and a separately versioned validator was used. Runner, prompt, packet, model revisions and decoding settings are unchanged.

## Reproduce — four levels, stated separately
| Level | What it reproduces | Command (from the artifact root) | Needs | Status in this release |
|---|---|---|---|---|
| A | Fig. 3 values, intervals, McNemar and ranking-check counts **recomputed from the released per-unit verdict table** (no execution, no scorer code) | `python3 studies/model_output_case_study/code/recompute_case_study.py` | Python 3 only | Tested in a clean copy: PASS |
| B | The 3 frozen question packets **rebuilt** from Mind the Query at the pinned commit and the released IDs (byte-identical), plus prediction and dump hashes | `bash third_party/fetch_mind_the_query.sh` then `python3 studies/model_output_case_study/code/reproduce_case_study.py prepare` | git, network (GitHub) | `prepare` tested on a local copy of the pinned checkout: PASS. The fetch script is unchanged from v1.2.2 |
| C | The **nine comparators re-run** at pinned commits on result pairs, then the per-unit table compared byte-for-byte with the released one | `bash third_party/fetch_scorers.sh`, then `… reproduce_case_study.py replay` and `… table` | network (GitHub), the pinned scorer environment (`environment/`) | Tested with the authors' recorded result pairs standing in for a live execution: unit table byte-identical, Table IX PASS |
| D | **End-to-end**: execute every gold and predicted query on the benchmark graphs with the frozen baseline (four read-only Neo4j 5.15.0 Community containers), then C | `docker pull neo4j:5.15.0`, then `… reproduce_case_study.py execute` (then `replay`, `table`) | Docker, ~4 GB RAM, network | Executed once by the authors (Session 55L). The release driver's `execute` stage has **not** been run from a clean copy of this release |

Notes:
- Raw result rows are not redistributed (the graph dumps have no licence file), so levels C and D for this study require executing the queries locally (level D).
- Model inference is not part of reproduction. The released predictions are the frozen model outputs, and regenerating them would need the pinned models on a GPU (`runtime/`).
- The `execute` stage checks the Neo4j image by tag, edition and version and records its image ID. The original run used the arm64 image, so the ID differs on other architectures.

## Contents and exclusions
- **Included:** `predictions/` (raw model outputs with per-row metadata and the Kaggle environment record), `verdicts/case_study_units.csv` (600 units: status and the verdict of every comparator), `frozen/` (question IDs, graph mappings with dump hashes, near-overlap flags), `policy/`, `runtime/`, `code/`.
- **Not included:** Mind the Query questions, gold queries, graph dumps and result rows (fetch them at the pinned commit); third-party scorer code (fetched at pinned commits); credentials; human labels. No labels exist yet; a 47-case blinded annotation packet is pending.
