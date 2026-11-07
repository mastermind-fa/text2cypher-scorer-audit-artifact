#!/usr/bin/env bash
# Reproduce the policy-sensitive feature exposure counts and the post-hoc provenance-by-dimension table (v1.2.0).
#   scripts/reproduce_exposure.sh [DATASET_DIR]
# Needs the pinned CypherTurn and Mind the Query sources (third_party/fetch_scorers.sh, third_party/fetch_mind_the_query.sh).
# No database, no network beyond those fetches. Writes only under rebuild/.
set -euo pipefail
cd "$(dirname "$0")/.."
S=studies/exposure_and_released_path; OUT=rebuild/exposure; mkdir -p "$OUT"
python3 -I $S/exposure/exposure.py --root "$PWD" --out "$OUT" > /dev/null
python3 - "$S/exposure/outputs/exposure_counts.csv" "$OUT/exposure_counts.csv" <<'PY'
import sys
a, b = (open(p).read() for p in sys.argv[1:3])
print("exposure counts:", "MATCH" if a == b else "MISMATCH"); sys.exit(a != b)
PY
DS=${1:-${DATASET_DIR:-}}
if [ -n "$DS" ]; then
  python3 -I $S/provenance_by_dimension/provenance_by_dimension.py \
    studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final/s3_results.csv "$DS/splits/record_splits.csv" > "$OUT/provenance_by_dimension.txt"
  cmp -s "$OUT/provenance_by_dimension.txt" $S/provenance_by_dimension/expected_output.txt \
    && echo "provenance by dimension: MATCH" || { echo "provenance by dimension: MISMATCH"; exit 1; }
else
  echo "provenance by dimension: SKIPPED (pass the dataset repository root)"
fi
echo "GQLBench live-server check: see $S/gqlbench_released_path/PROTOCOL.md (needs Docker and the rebuilt S20 cases)."
