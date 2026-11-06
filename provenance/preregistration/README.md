# Pre-specified protocol: what can and cannot be verified

`k4-protocol-v1.md` is the protocol of the corpus audit (research questions, scorers, adapter contract, the controlled
suite, the hypothesis with its 2% threshold and Bonferroni-Wilson rule, execution order), reproduced byte-for-byte from
lines 138–251 of a session record in the authors' private Git repository.
`PREREGISTRATION_EVIDENCE.json` gives the identifiers.

**Checkable from this repository:**
- the protocol text and its SHA-256;
- the protocol names the controlled-suite file by SHA-256 (`80d0fd3f…`), and the released
  `studies/controlled_suite/audit/s1/s1_cases.jsonl` has exactly that hash;
- every number in the paper follows from the frozen verdicts under the protocol's stated rule (`reproduce.sh --quick`).

**Recorded, but not independently verifiable:**
- the protocol was committed and tagged (`session12-k4-protocol-v1`, commit `79e318aa964a`, 2026-10-30T00:09:21+06:00)
  before the readiness run (2026-10-30T00:24:34+06:00) and the main audit run (2026-10-30T01:09:54+06:00; frozen run
  directory stamped 2026-10-29T19:04:31Z);
- these timestamps come from the authors' private Git history, which is not public, and Git timestamps are set by the
  committer;
- the protocol was not lodged with a public registry. The earliest third-party timestamp for this material is GitHub's
  record of the first push of this repository (2026-11-02), which is after the runs.
