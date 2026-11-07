#!/usr/bin/env bash
# Artifact entry point (artifact v1; paper-facing layer added in the final repair). See README.md.
#   ./reproduce.sh --quick [DATASET_DIR]   R0: recompute every manuscript number from released frozen verdicts and compare
#                                          it with expected_outputs/paper_result_manifest.json (corrected controlled suite,
#                                          both Text2GQL evaluators, model-level table, corpus, native suites). No network.
#                                          Without DATASET_DIR (root of the released dataset repository) the claims that
#                                          need its ID files are reported as BOUNDARY and the run is PARTIAL, not PASS.
#   ./reproduce.sh --full DATASET_DIR      R0 + R1 + R2: fetch the pinned scorers and Mind the Query; re-score the
#                                          corrected (paper-facing) and original (superseded) controlled suites, the corpus
#                                          and model-output pairs; re-run the second Text2GQL evaluator; rebuild the
#                                          model-level table from released IDs; rebuild and re-score the native-Cypher
#                                          suites with a throwaway Neo4j 5.15.0 (Docker); then require every manifest claim.
#   ./reproduce.sh --legacy-quick          the v1.0.0 quick checks (quick_check.py: ORIGINAL controlled suite, superseded;
#                                          paper_numbers.py: ten headline numbers), kept as a record
# DATASET_DIR may also be given as DATASET_DIR or CORPUS_PAIRS_DIR in the environment. Writes only under rebuild/.
set -euo pipefail
cd "$(dirname "$0")"; PY=${PYTHON:-python3}
MODE=${1:---quick}; DS=${2:-${DATASET_DIR:-${CORPUS_PAIRS_DIR:-}}}
[ -n "$DS" ] && DS=$(cd "$DS" && pwd)
pairs() { for c in "$DS/$1" "$DS/corpus/$1" "$DS/model_outputs/$1"; do [ -f "$c" ] && { echo "$c"; return; }; done; echo "$DS/$1"; }
dsarg() { [ -n "$DS" ] && echo "--dataset $DS"; true; }
case "$MODE" in
  --quick) $PY scripts/paper_check.py $(dsarg) ;;
  --legacy-quick) echo "NOTE: the v1.0.0 quick checks. quick_check.py verifies the ORIGINAL controlled suite (superseded; the"
                  echo "      paper reports the corrected suite); paper_numbers.py checks ten headline numbers (all covered by --quick)."
                  $PY scripts/quick_check.py && CORPUS_DIR="$DS" $PY scripts/paper_numbers.py ;;
  --full)
    [ -n "$DS" ] || { echo "usage: $0 --full DATASET_DIR   (the released dataset repository is required for a full reproduction)"; exit 64; }
    $PY scripts/paper_check.py --dataset "$DS"
    bash third_party/fetch_scorers.sh
    bash third_party/fetch_mind_the_query.sh
    $PY scripts/full_rescore.py s1_corrected
    $PY scripts/full_rescore.py s1
    $PY scripts/full_rescore.py s3 "$(pairs s3_pairs.jsonl)"
    $PY scripts/full_rescore.py s2 "$(pairs s2_pairs.jsonl)"
    $PY scripts/text2gql_reference.py --dataset "$DS" --require s1_corrected s1_original s3 s2
    $PY scripts/model_level_from_ids.py "$(pairs s2_not_scored_units.json)"
    command -v docker >/dev/null || { echo "BOUNDARY: Docker not found; native-Cypher rebuilds (R2) not run — this is NOT a full reproduction"; exit 2; }
    bash scripts/full_native.sh s18
    bash scripts/full_native.sh s20
    bash scripts/full_native.sh s23
    $PY scripts/text2gql_reference.py --require s18 s20 s23
    $PY scripts/paper_check.py --dataset "$DS" --require-all
    echo "FULL REPRODUCTION: PASS (R0 + R1 + R2; every manifest claim checked)" ;;
  *) echo "usage: $0 --quick [DATASET_DIR] | --full DATASET_DIR | --legacy-quick"; exit 64 ;;
esac
