# S49 — GQLBench numeric-NULL rejection through the released materialisation path (protocol)

Frozen before execution, 2026-11-07. Nothing below was run when this file was written.

## Question
Does GQLBench's released Cypher path — its own `cypher_execute()` calling the real `neo4j` driver with
`result_transformer_=neo4j.Result.to_df` against a live Neo4j server, followed by its unmodified `itertuples`
conversion and `res_eq` — reject two different query texts whose results are identical when a numeric column
contains NULL? Until now the claim rested on the S13/S20 adapter, which replaces `GraphDatabase` with a replay
object that returns `pd.DataFrame(rows, columns=keys)` (stated to equal `Result.to_df(expand=False)` in driver 5.26.0).

## Frozen identities
| Item | Value |
|---|---|
| Upstream | https://github.com/qxssadf/GQLBench @ `fb9d5a9be3ccc73ea9fe44c67a9b180eccedfad2` |
| Scorer file | `Code/eval/execute_accuracy.py`, SHA-256 `39604c2786bc5e780eaa53942ce2d5184deb323390c676737879d22e686d7c16` |
| Functions exercised, unmodified | `execution_accuracy` → `cypher_execute` (real `GraphDatabase.driver`, `execute_query(..., result_transformer_=neo4j.Result.to_df)`, `itertuples`, `cypher_value_to_python_value`) → `res_eq` → `quick_rej` |
| Neo4j server | Docker image `neo4j:5.26.28` (already local), throwaway container, no volumes or bind mounts, auth set by env var, ports 7687 only on localhost |
| Python / driver / pandas / numpy | 3.12.15 / neo4j 5.26.0 / pandas 2.3.3 / numpy 2.5.3 (project `.venv`) |
| `Result.to_df(expand=False)` source in driver 5.26.0 | `pd.DataFrame(self.values(), columns=self._keys)` |
| Test case | S20-69098610ca (CypherTurn graph `magic_academy`, D5 NULL class); `cases.jsonl` SHA-256 `5e210cde8516f1a36b06db9a279b34d422c73a8ed97ab55612d06fcf338ddaad` |

## Only deviations from the released path (stated in advance)
1. `nebulagraph_python` is not installed; empty placeholder modules are registered so the module imports. The
   NebulaGraph branch is never called on the Cypher path (same stub as the S13 adapter).
2. Credentials come from module globals set after import (`ea.NEO4jUSERNAME`, `ea.NEO4jPASSWORD`); the upstream
   `Config.py` is not edited. The URI `bolt://localhost:7687` is upstream's hard-coded value.
3. `db_name="neo4j"` (Community edition has one user database). `Import_Graph_Data_neo4j.db_name` maps it unchanged.
4. The CypherTurn graph is NOT loaded (that would be a mutating Neo4j operation). Instead each side runs a read-only
   query that emits the frozen result rows of the case through the server:
   `UNWIND $rows`-free literal form `UNWIND [[0,'Archmage Theron',1285], ...] AS r WITH r ORDER BY r[0] RETURN r[1] AS name, r[2] AS p_opt`
   (reference) and the same with `coalesce(r[2], null) AS p_opt` (prediction). The values reach the driver as Bolt
   records exactly as a graph query's would (STRING / INTEGER / NULL), so the materialisation path is identical;
   only the way the server produces the rows differs. Both texts contain `ORDER BY`, as the original reference does,
   so `order_matters=True` exactly as in the frozen case. `time.sleep` (0.1 s pacing) is left in place.

## Runs (all read-only)
| Run | Rows | Expected if the S20 claim is right |
|---|---|---|
| R1 flagship | frozen 29 rows, 12 NULLs in integer column `p_opt` | reject (`False`) |
| R2 same rows, no `ORDER BY` in either text (`order_matters=False`, set path) | as R1 | reject |
| R3 control: NULLs replaced by 0 | no NULL | accept |
| R4 control: NULL only in a string column | name column NULL in 3 rows, ints kept | accept (object dtype keeps `None`) |
| R5 identical query text | as R1 | accept via the text-equality shortcut, no execution |

For each run, record: verdict and message, the DataFrame dtypes produced by the real `Result.to_df`, the Python
types and `id()` distinctness of the NULL cells after `itertuples`, and whether `quick_rej` or the permutation loop
decided.

## Outcome rule (fixed now)
- **A — confirmed:** R1 and R2 reject, R3 and R4 accept. Manuscript may say the rejection was reproduced through
  GQLBench's own execution path with the real driver and `Result.to_df`.
- **B — adapter-only artifact:** R1 accepts. Stop; audit and correct every manuscript statement that relies on it.
- **C — cannot execute faithfully:** container/driver failure. Report; no claim upgrade.
Controls failing (R3 or R4 reject) → record and explain before any manuscript use.
