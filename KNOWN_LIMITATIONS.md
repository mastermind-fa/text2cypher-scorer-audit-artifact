# Known limitations
- **Controlled fixtures** are mechanism probes: they establish that a rule exists and what it causes, not how often it
  occurs.
- **Corpus pairs** share one domain, one graph and one authoring process. Disagreement concentrates in the 99
  project-written records (20/99 versus 21/464 non-unanimous).
- **One scorer, CypherLens,** parses the candidate's query text and cannot parse SQL, so it is out of its input domain
  on SQL–Cypher pairs.
- **Model outputs** come from two small models at floor accuracy. No ranking effect is demonstrated.
- **Natural NULLs** are rare; maps and nested values are covered only by controlled fixtures. Graph-valued results
  (nodes, paths) are not tested.
- **Verdicts** are one-instance result comparisons. An acceptance does not prove query equivalence.
- **CypherTurn rebuilds** are verdict-level, not byte-level.
- **The Cypher translations' authoring process** could not be reconstructed from the available records. All were
  validated by execution against the SQL results.
