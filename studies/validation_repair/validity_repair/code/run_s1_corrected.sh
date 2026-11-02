#!/usr/bin/env bash
# Score the query-consistent controlled suite once with every scorer through the FROZEN runner v1.1 (the validation repair).
set -euo pipefail
cd "$(dirname "$0")/../../../.."
D=studies/validation_repair/validity_repair/s1_corrected
for s in cypherturn cypherbench gqlbench tugraph pipecypher cypherlens cyspider neo4jlabs pc_v1_1; do
  PYTHONHASHSEED=0 python3.12 studies/corpus_audit/audit_analysis/code/run_experiment_v1_1.py "$s" s1 "$D/s1_corrected_cases.jsonl" "$D/results/$s.jsonl"
done
