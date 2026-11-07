#!/usr/bin/env bash
# Reproduce the policy-sensitive feature exposure counts, the post-hoc provenance-by-dimension table and Figure 1.
#   scripts/reproduce_exposure.sh [DATASET_DIR]
# Needs the pinned CypherTurn and Mind the Query sources (third_party/fetch_scorers.sh, third_party/fetch_mind_the_query.sh).
# Result-level Mind the Query counts are checked only after studies/exposure_and_released_path/exposure/mtq_results/
# run_mtq_gold.sh has produced the gold results (Docker). No network beyond the fetches. Writes only under rebuild/.
set -euo pipefail
cd "$(dirname "$0")/.."
S=studies/exposure_and_released_path; R=$S/exposure/mtq_results; OUT=rebuild/exposure; mkdir -p "$OUT"
check() { cmp -s "$1" "$2" && echo "$3: MATCH" || { echo "$3: MISMATCH"; exit 1; }; }
python3 -I $S/exposure/exposure.py --root "$PWD" --out "$OUT" > /dev/null
if [ -f "$R/mtq_gold_results.jsonl" ]; then
  (cd "$R" && shasum -a 256 -c mtq_gold_results.sha256 >/dev/null) && echo "Mind the Query gold results: hash MATCH" \
    || { echo "Mind the Query gold results: hash MISMATCH"; exit 1; }
  check "$OUT/exposure_counts.csv" $S/exposure/outputs_mtq_result_level/exposure_counts.csv "exposure counts (query and result level)"
  python3 - "$OUT/exposure_counts.csv" $S/exposure/outputs/exposure_counts.csv <<'PY'
import csv, sys
a, b = (list(csv.DictReader(open(p))) for p in sys.argv[1:3])
q = lambda rows: [r for r in rows if r["level"] == "query" or not r["population"].startswith("Mind the Query")]
print("query-level counts (v1.2.0 outputs):", "MATCH" if q(a) == q(b) else "MISMATCH"); sys.exit(q(a) != q(b))
PY
else
  check "$OUT/exposure_counts.csv" $S/exposure/outputs/exposure_counts.csv "exposure counts (query level; result level needs run_mtq_gold.sh)"
fi
DS=${1:-${DATASET_DIR:-}}
if [ -n "$DS" ]; then
  python3 -I $S/provenance_by_dimension/provenance_by_dimension.py \
    studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final/s3_results.csv "$DS/splits/record_splits.csv" > "$OUT/provenance_by_dimension.txt"
  check "$OUT/provenance_by_dimension.txt" $S/provenance_by_dimension/expected_output.txt "provenance by dimension"
else
  echo "provenance by dimension: SKIPPED (pass the dataset repository root)"
fi
python3 -I $S/figure1/render_figure1.py > /dev/null
git diff --quiet -- $S/figure1/figure1_s3_heatmap.png 2>/dev/null && echo "figure 1: re-rendered byte-identical" \
  || echo "figure 1: re-rendered (compare with the released PNG; matplotlib versions may differ)"
echo "GQLBench live-server check: see $S/gqlbench_released_path/PROTOCOL.md (needs Docker and the rebuilt S20 cases)."
