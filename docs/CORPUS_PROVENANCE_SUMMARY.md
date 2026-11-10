# Corpus provenance summary (563 SQL–Cypher pairs; details in the dataset release's DATA_PROVENANCE.md and provenance/)

| Part | Count | Origin | Licence / permission | Verification |
|---|---:|---|---|---|
| Questions + SQL matching BIRD's official training release | 383 | BIRD `works_cycles` | CC BY-SA 4.0, attribution | exact match to the official release |
| Questions + SQL matching BIRD's full training file | 81 | BIRD (via a public mirror of the full file) | CC BY-SA 4.0, attribution | exact match to the mirror; not to the official release |
| Questions + SQL written for the project | 99 | five-member project annotation team | authorization **reported by the authors** (2026-11-07); no written authorization document is stored in the repository | contributors' own material only |
| Cypher translations | 563 | project translations | released with the corpus | admitted only if SQL and Cypher outputs matched under the corpus validation comparator, **whose code was not preserved**; the admission decisions cannot be reconstructed independently, though every stored result can be regenerated from BIRD's database with `graph_conversion/` |
| Property graph | 1 | converted from BIRD's `works_cycles` SQLite database by an author's script (`graph_conversion/`) | Apache-2.0 (script) | rebuilt graph content-identical to the original |

**Limits.** Disagreement concentrates in the 99 project-written records (paper Section VI). Conclusions that depend on them are reported separately; on the 383 official-release records, no scorer pair meets the detection criterion. No part of the translation process beyond the stored records and the validation outcome is claimed to be reconstructed.
