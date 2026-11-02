# Text-to-Cypher Result-Equivalence Reporting Card (proposal, study S18)

**What it is.** A one-table disclosure that benchmark authors can include so that "execution accuracy" is reproducible
and comparable.
- It documents the comparator's policy; it is **not** a new metric.
- Each dimension corresponds to a policy that the MAIN_AUDIT audit (S1 / S3) showed to vary across released scorers.

## Card (fill one per benchmark scorer)

| Dimension | Required disclosure (choose / specify) |
|---|---|
| Column names | strict match / ignored / normalised (how) |
| Aliases | result keys used as-is / ignored / parsed from query text |
| Column order | positional / permutation-invariant / aligned by name |
| Row order | always compared / only when ORDER BY / never |
| ORDER BY trigger | detected in gold text / prediction text / either / n.a. |
| Duplicate rows | multiset (bag) / set |
| NULL handling | exact / normalised (to what) |
| Numeric types | strict (1 ≠ 1.0) / coerced (1 = 1.0) |
| Float tolerance | exact / rounding (digits) / epsilon (value) |
| Strings | raw / normalised (case, whitespace) |
| Lists / maps | structural (ordered / unordered) / serialised to string |
| Graph values (nodes, relationships, paths) | element ID / properties / unsupported |
| Empty results | equal if both empty / special rule (specify) |
| Query-text dependency | none / yes (what is parsed) |
| Identical query strings | compared normally / short-circuit pass |
| Errors and timeouts | scored 0 / excluded / reported separately |
| Determinism | deterministic / seeded (seed) / stochastic |
| Materialisation | driver records / DataFrame / other (library + version) |
| Version | repository + commit + file + function |

## Example: the seven audited scorers (from code at the pinned commits; see paper Table 1)

| Dimension | CypherTurn | CypherBench | GQLBench | Text2GQL driver | PIPE-Cypher | CypherLens | CySpider |
|---|---|---|---|---|---|---|---|
| Column names | strict | ignored | ignored | ignored | ignored (1 col) / strict (≥ 2) | aligned via parsed aliases | ignored |
| Column order | ignored (sorted keys) | permutation search | permutation search | positional | ignored | aligned | positional |
| Row order | never | if `order by` in gold | if `order by` in gold | if `order by` in prediction | never | never | never |
| Duplicates | multiset | multiset | multiset | multiset | set | per-column multiset | set |
| Numeric types | strict (`str`) | coerced | coerced (pandas) | coerced; 9-dp rounding | strict (`str`) | `str`; tolerant to tiny drift | coerced |
| Lists / maps | `str` | lists sorted | ordered tuples | ordered tuples | `str` | `str` | unsupported (exception) |
| Query-text dependency | no | `order by` + identical-string shortcut | `order by` + identical-string shortcut | `order by` (prediction) | no | **yes (RETURN aliases)** | no |
| Empty results | pass if both empty | pass if both empty | pass if both empty | pass if both empty | pass if both empty | pass if both empty | pass if both empty |
| Version | BarryQ/CypherTurn @9d9528e1 | megagonlabs/cypherbench @4cc727d2 | qxssadf/GQLBench @fb9d5a9b | ldbc/Text2GraphQuery-Driver @ab296fab | suraj-ranganath/PIPE-Cypher @0f127208 | YasmeanMohammadi/cypherLenz @ce648194 | 22842219/SemanticParser4Graph @6cd5eff4 |

Machine-readable form: `paper/result_equivalence_reporting_card.yaml`.
