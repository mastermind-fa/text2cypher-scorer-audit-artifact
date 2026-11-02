# Validation notes

## Controlled fixtures: query-consistent correction
- **Issue.** In some controlled fixtures, the query texts did not match the result columns. Some aliases in a query
  were inconsistent with the column names of its result, and some fixtures used identical query text for reference
  and candidate. This matters for scorers that read query text.
- **Correction.** 36 fixtures were corrected:
  - 32 had alias-inconsistent texts;
  - 9 used identical texts;
  - 5 fall in both groups;
  - in 16 fixtures a bound variable is renamed.

  The result rows, labels and classes are unchanged. The correction rules were fixed before any re-scoring.
- **Validation.** The corrected suite was scored once with every scorer through the frozen runner. The 85 unaffected
  fixtures reproduced every frozen verdict. The original suite and its verdicts are kept unchanged alongside the
  corrected ones (`studies/controlled_suite/`, `studies/validation_repair/validity_repair/s1_corrected/`).

## Text2GraphQuery: two released evaluators
The Text2GraphQuery repository releases two evaluators: the pipeline evaluator, audited throughout, and a standalone
reference script. The reference script was run verbatim on every frozen result pair as an additional comparison. It
compares sets and never checks order (`studies/validation_repair/validity_repair/text2gql/`).

## Native-Cypher rebuilds
- **Mind the Query:** rebuilds are byte-identical.
- **CypherTurn:** rebuilds match at verdict level. The oracle may admit a slightly different case set when Neo4j load
  order differs; `scripts/compare_verdicts.py` reports this.
