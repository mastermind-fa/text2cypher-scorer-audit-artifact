#!/usr/bin/env bash
# Artifact entry point (artifact v1). See README.md.
#   ./reproduce.sh --quick     recompute every reported number from released frozen verdicts; no Neo4j, no downloads
#   ./reproduce.sh --full      fetch pinned scorers + public benchmarks; re-score S1; rebuild + re-score the native-Cypher
#                              studies with a throwaway Neo4j (Docker); S2/S3 re-scoring runs only if the corpus pairs
#                              are present (CORPUS_PAIRS_DIR); otherwise that boundary is reported, not hidden.
set -euo pipefail
cd "$(dirname "$0")"; PY=${PYTHON:-python3}
case "${1:---quick}" in
  --quick) $PY scripts/quick_check.py ;;
  --full)
    $PY scripts/quick_check.py
    bash third_party/fetch_scorers.sh
    bash third_party/fetch_mind_the_query.sh
    $PY scripts/full_rescore.py s1
    if [ -n "${CORPUS_PAIRS_DIR:-}" ]; then
      $PY scripts/full_rescore.py s3 "$CORPUS_PAIRS_DIR/s3_pairs.jsonl"
      $PY scripts/full_rescore.py s2 "$CORPUS_PAIRS_DIR/s2_pairs.jsonl"
    else
      echo "BOUNDARY: S2/S3 re-scoring skipped (set CORPUS_PAIRS_DIR to the released corpus pairs)"
    fi
    command -v docker >/dev/null || { echo "BOUNDARY: Docker not found; native-Cypher rebuilds skipped"; exit 0; }
    bash scripts/full_native.sh s18
    bash scripts/full_native.sh s20
    bash scripts/full_native.sh s23 ;;
  *) echo "usage: $0 --quick|--full"; exit 64 ;;
esac
