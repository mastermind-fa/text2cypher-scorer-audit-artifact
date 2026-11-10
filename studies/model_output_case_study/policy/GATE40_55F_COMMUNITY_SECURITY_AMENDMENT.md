# Session 55F — Community Neo4j feasibility and proposed security amendment (OWNER REVIEW)

**Verdict: READY FOR OWNER REVIEW — COMMUNITY SECURITY AMENDMENT** (conditional: the live write-denial probe, Authorization C, must pass or this route reverts to BLOCKED). Nothing was started, restored, executed or accepted in S55F. Track A is untouched.

## 1. Evidence labels

**PROJECT FACT (verified this session):**
- Archive `s55_gate40_5rcjfasx_artifacts.zip` SHA-256 `ae212509…26e1` matches. `offline-check` passes with 40 packet rows, 40 predictions per model and 30/9/1 questions for er/wwc/healthcare.
- Frozen `project_ex.py` (`58920a41…`) and `score_predictions.py` (`38175e99…`) are byte-identical to the pinned hashes. S55F modified neither.
- The three hash-pinned dumps exist in repo-local `external/mind_the_query/Datasets/` (git-ignored) and match the manifest hashes. **The `/private/tmp/session55-native-r2.Iy7Kt0` path cited in S55D/S55E commands and historical tests no longer exists.** Use `--dump-root external/mind_the_query/Datasets`.
- Local images: `neo4j:5.15.0` Community, ID `345d13bb…49512c`, arm64, `NEO4J_EDITION=community`; and the Enterprise image (not used).

**PAPER/DOC FACT (official Neo4j 5-branch docs, read by subagent; the pages show 2026.10/5.26, not a 5.15 page):**
- Community has exactly one standard database. This is why one DBMS cannot host three graphs.
- `server.databases.read_only`, `server.databases.default_to_read_only`, `dbms.security.procedures.allowlist`, `db.transaction.timeout`, the memory limits, `server.http.enabled` and `server.bolt.listen_address` are listed with no Enterprise marking. The docs do not state that they work in Community 5.15.
- The RBAC pages are labelled Enterprise; user management in Community is "limited".
- `elementId()` carries no stability guarantee across restores.

**UNVERIFIED (needs a live test):** that Community 5.15 enforces the read-only settings, the error code for a denied write, whether `neo4j-admin database load neo4j` works as scripted, and whether the frozen `elementId`-based fingerprint reproduces.

## 2. Community vs Enterprise

| | A. Three Community 5.15 containers | B. Enterprise 5.15 (image already pulled) |
|---|---|---|
| Licence | Community server (GPLv3 per Neo4j; not re-verified in S55F); no acceptance flag set; $0 | **Not established** for standalone Docker research use (S55E). Cannot be resolved by engineering |
| Graph isolation | Strong: separate container, volume, port and credential per graph | Three DBs in one DBMS |
| Write prevention | Server-side read-only mode **if honoured** (live gate), plus query admission, plus detection | Database-enforced `reader` role, plus `READ ONLY` databases |
| Privilege separation | **None.** Every credential is admin-equivalent | Yes |
| Blocking issue | Security gap documented below; owner decision | Licence eligibility |

**Recommendation:** use A, because it is the only $0 path that can be started without an unresolved legal question, provided the owner accepts the amendment below. Choose B only if the owner obtains an explicit Neo4j entitlement; the 55E tooling stays valid for that case.

## 3. Proposed amendment: security policy `S55F-community-v1`

**Scope.** Disposable, local, single-user scoring of 80 frozen model outputs plus 40 reference queries on three public benchmark graphs. No production DB, no secrets in graphs, no sharing of the endpoint.

**Controls, in two classes:**
- **Prevention, server-side if live-verified:** read-only mode for the single database; HTTP/HTTPS connectors disabled; Bolt published only to `127.0.0.1` on a unique port per graph; procedure allowlist limited to `dbms.components`; `LOAD CSV` from file URLs off; 30 s transaction timeout and per-transaction memory caps server-side; container `--cap-drop=ALL`, `no-new-privileges`, 1 GiB memory, 1 CPU and a PID limit; restore container runs with `--network=none`.
- **Prevention, client-side (not database-enforced):** the frozen `read_only_query` gate, plus a namespace gate (`gds./apoc./dbms./jwt.`), run inside every transaction; READ-only sessions; `RoutedDriver` refuses unknown or unverified graphs.
- **Detection / fail-closed:** frozen fingerprint check before scoring; stable (ID-free) content snapshot before and after scoring; any difference aborts before any output is written; write-denial probe at preflight.

**Residual gaps, stated plainly:**
1. **No database-enforced least privilege.** Possession of the password means admin. If the read-only setting is not honoured, nothing server-side stops a write; admission and detection only reduce and detect it. This is the reason for the conditional verdict.
2. **No network-egress block.** The container sits on Docker's default bridge. Exfiltration or SSRF would require a query that passes admission, and none of the admitted forms can open connections (no `CALL`, `LOAD` or plugins loaded). The lexical gate is a filter, not a parser.
3. The lexical gate can mis-classify unusual valid text. The behaviour is unchanged from the frozen evaluator, and rejections are recorded per query.
4. Simulated tests cannot show live behaviour.
5. Passwords sit in process environments and `docker inspect` output on the owner's machine. Acceptable for single-user, disposable use.

**Acceptance rule (pre-specified):** Authorization C must show on all three containers (i) edition Community 5.15.0, (ii) frozen fingerprint equality, (iii) rollback-only `CREATE` rejected with a server error code in `{ForbiddenOnReadOnlyDatabase, Security.Forbidden}`, (iv) ports bound to loopback only (`docker port`, `lsof`), (v) no HTTP listener. **Any failure means STOP, status BLOCKED — Enterprise or other verified solution required.** No post-hoc waiver. A fingerprint mismatch, including one caused purely by `elementId`, also stops the run and goes to the owner. The code never auto-waives it. `stable_snapshot` is recorded for diagnosis only.

**Does not change:** metric semantics, model predictions, prompts, packet membership or the 6/40 gate. The 55D `route_map` still demands the frozen logical names `s55er/s55wwc/s55health`. `RoutedDriver` translates each to its own container's single `neo4j` database, so the frozen executor is reused unchanged.

## 4. Offline quality-gate results (EXECUTED RESULT, synthetic only)

`test_community_55f.py`: 24/24 pass. Coverage:
- three-graph routing, with each graph reaching only its own fake container and READ mode only;
- wrong or unknown graph rejection;
- unverified-graph block;
- WRITE-mode refusal;
- route aliasing and missing routes;
- timeout passed to every transaction;
- timeout treated as `invalid_reference`, never as a model error;
- 12 unsafe query forms rejected, including inside the transaction wrapper;
- static policy check of the generated `docker run` argv;
- port, volume and container collisions;
- hash mismatch and missing dump;
- password rules;
- both authorizations required before any Docker call;
- no destructive commands in source;
- resources retained on failure;
- preflight fail-closed on edition, version, fingerprint, accepted write and unexpected error code;
- mutation detection aborting before output.

Mutation checks: disabling the admission gate made 2 tests fail, and disabling the collision check made 1 test fail.

Whole evaluation directory: 74 tests, 72 pass, 2 skipped. The 2 errors are the historical 55D tests that hard-code the deleted `/private/tmp` dump path. This is an environmental defect and not a logic defect. Those files are checksum-recorded and were left unchanged. They pass when the path exists. The `plan` command and the routing `offline-check` also pass. **These tests do not establish live database security.**

## 5. Next owner authorizations (separate; none inferred)

Run from the repo root. Passwords are generated outside the repository, in your shell only:

```bash
export S55F_PW_ER="$(openssl rand -base64 24)" S55F_PW_WWC="$(openssl rand -base64 24)" S55F_PW_HEALTH="$(openssl rand -base64 24)"
```

**A. Approve amendment `S55F-community-v1`.** Reply verbatim: *"I approve Community security amendment S55F-community-v1 for Gate40, including the residual gaps listed."* This is a decision only; it runs nothing.

**B. Disposable container creation and graph restoration.** Reply: *"Run S55F provisioning."* The command uses local CPU, disk and Docker only, with no GPU, API or paid quota. It creates three containers and three volumes (the `s55f-gate40-*` set) and restores each dump into its own volume. It is not run until you say so:
```bash
.venv/bin/python research_control/session55/TRACK_B_NEW_EXPERIMENTS/evaluation/provision_community_55f.py execute --dump-root external/mind_the_query/Datasets --owner-authorized-deployment --owner-authorized-security-amendment
```

**C. Live integration and security tests.** Reply: *"Run S55F live preflight."* The command does not execute any Gate40 query; it reads graphs, runs the fingerprints and does the rollback-only write probe. **This is the gate that decides whether the amendment stands.**
```bash
.venv/bin/python research_control/session55/TRACK_B_NEW_EXPERIMENTS/evaluation/gate40_workflow_55f.py community-preflight --owner-authorized-live --mtq-source external/mind_the_query --dump-root external/mind_the_query/Datasets --output-dir research_control/session55/TRACK_B_NEW_EXPERIMENTS/gate40_scoring_runs/s55f_preflight_01
```
Separately run `docker port s55f-gate40-er` (and `-wwc`, `-health`) and `docker exec s55f-gate40-er ss -ltn`, to confirm there is no HTTP listener.

**D. Score the 80 frozen predictions.** Reply: *"Run S55F Gate40 scoring."* Only after C passes. It uses local CPU only and writes a new exclusive directory plus a ZIP:
```bash
.venv/bin/python research_control/session55/TRACK_B_NEW_EXPERIMENTS/evaluation/gate40_workflow_55f.py score --owner-authorized-live --mtq-source external/mind_the_query --dump-root external/mind_the_query/Datasets --output-dir research_control/session55/TRACK_B_NEW_EXPERIMENTS/gate40_scoring_runs/s55f_score_01
```

Resource estimate for B–D: CPU, 3 GB RAM for the three containers at the same time, under 1 GB disk, roughly 10–20 min including restore, no API key, $0. Cleanup of the six `s55f-gate40-*` resources needs its own explicit approval; there is no cleanup command.

## 6. Open risks to decide, not resolved here
- Whether `neo4j-admin database load neo4j` plus read-only-from-first-start works on 5.15 Community (live-only).
- Whether the `elementId` fingerprint reproduces under a fresh DBMS. If it does not, the owner decides whether to accept a separately documented content-identity argument. `stable_snapshot` hashes cannot be compared with the frozen values, because none were recorded.
- The 55D/55E documents' claim that "Community users have implied admin privileges" is not confirmed by the pages the subagent read. The "limited user management" statement is verified.
