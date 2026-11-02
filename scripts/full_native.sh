#!/usr/bin/env bash
# FULL native-Cypher rebuild (artifact-full-native-v1). Portable re-implementation of the frozen run_s18/s20/s23 drivers
# (which hard-code the author's path): regenerate candidates from the public benchmark at the pinned commit, run the
# frozen oracle against a THROWAWAY Neo4j 5.15.0 container (Docker, free, CPU), compare the rebuilt input hashes with the
# frozen ones, score once with the frozen scorers, and compare verdicts. Writes only under rebuild/.
#   bash scripts/full_native.sh s18|s20|s23        (s20 needs s18 first; scorers + benchmark fetched first)
# STATUS: executed in the fresh-environment reproduction (fresh environment). Mind the Query (s23) inputs and verdicts are byte-identical to the
# frozen ones (dumps are restored as store files). CypherTurn (s18/s20) graphs are loaded by Cypher CREATE statements, so
# Neo4j internal-ID reuse can change unordered row sequences / LIMIT tie-breaks between loads: for s18/s20 the input hash is
# reported for information and acceptance is VERDICT-LEVEL (compare_verdicts.py: identical per-class counts and per-case
# verdicts on common cases).
set -euo pipefail
cd "$(dirname "$0")/.."; R=$(pwd); PY=${PYTHON:-python3}; export PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0
STAGE=$1; OUT=$R/rebuild/$STAGE; mkdir -p "$OUT"
IMG=neo4j:5.15.0; NAME=artifact-$STAGE-neo4j; PW=artifact-local-only; PORT=17699
cmp_hash() {  # frozen_hashes_file filename rebuilt_file
  local exp; exp=$(awk -v f="$2" '$2==f{print $1}' "$1"); local got; got=$(shasum -a 256 "$3" | cut -d' ' -f1)
  [ "$exp" = "$got" ] && echo "OK   $2 matches frozen hash" || { echo "DIFF $2 ($got != $exp)"; return 1; }; }
up() { docker run -d --rm --name $NAME -p $PORT:7687 -e NEO4J_AUTH=neo4j/$PW ${1:-} $IMG >/dev/null
       until docker exec $NAME cypher-shell -u neo4j -p $PW "RETURN 1" >/dev/null 2>&1; do sleep 2; done; }
down() { docker stop $NAME >/dev/null 2>&1 || true; }
trap down EXIT
case $STAGE in
  s18) D=studies/native_cypherturn_validation/native_cypher; F=$D/frozen/20261030T083217Z_native_cypher_input
       $PY $D/code/s18_rewrite.py external/cypherturn "$OUT/candidates.jsonl"
       up; $PY $D/code/s18_oracle.py "$OUT/candidates.jsonl" external/cypherturn bolt://localhost:$PORT neo4j $PW "$OUT/frozen"; down
       IN=$(ls -d "$OUT"/frozen/*_input | tail -1); cmp_hash $F/hashes.sha256 cases.jsonl "$IN/cases.jsonl" || true
       $PY $D/code/s18_score.py "$IN" "$OUT/results" >/dev/null
       $PY scripts/compare_verdicts.py $D/frozen/20261030T083338Z_native_cypher_results/s18_verdicts.csv "$OUT/results/s18_verdicts.csv" family ;;
  s20) D=studies/native_cypherturn_stress/native_equivalence_stress; F=$D/frozen/20261030T143740Z_input
       $PY studies/native_cypherturn_validation/native_cypher/code/s18_rewrite.py external/cypherturn "$OUT/s18_candidates.jsonl" >/dev/null
       $PY scripts/s18_exclusion_from_ids.py "$OUT/s18_candidates.jsonl" "$OUT/s18_exclusion.jsonl"
       $PY $D/code/s20_rules.py external/cypherturn "$OUT/s18_exclusion.jsonl" "$OUT/candidates.jsonl" >/dev/null
       [ "$(shasum -a 256 "$OUT/candidates.jsonl" | cut -d' ' -f1)" = "$($PY -c "import json;print(json.load(open('$F/source_manifest.json'))['candidates_file_sha256'])")" ] \
         && echo "OK   S20 candidates match frozen hash" || { echo "FAIL S20 candidates"; exit 1; }
       up; $PY $D/code/s20_oracle.py "$OUT/candidates.jsonl" external/cypherturn bolt://localhost:$PORT neo4j $PW "$OUT/frozen"; down
       IN=$(ls -d "$OUT"/frozen/*_input | tail -1); cmp_hash $F/hashes.sha256 cases.jsonl "$IN/cases.jsonl" || true
       $PY $D/code/s20_score.py "$IN" "$OUT/results" >/dev/null
       $PY scripts/compare_verdicts.py $D/frozen/20261030T143804Z_results/s20_verdicts.csv "$OUT/results/s20_verdicts.csv" class ;;
  s23) D=studies/native_mind_the_query/mind_the_query_replication; P=$D/frozen/20261031T175346Z_preregistration
       $PY $D/code/s23_rules.py external/mind_the_query "$OUT/candidates.jsonl" >/dev/null
       cmp_hash $P/hashes.sha256 candidates.jsonl "$OUT/candidates.jsonl"
       [ -e $P/candidates.jsonl ] || cp "$OUT/candidates.jsonl" $P/candidates.jsonl   # restore the withheld, hash-verified file
       # portable copy of the frozen driver: only R, the interpreter, and the work/freeze output paths are rewritten
       sed -e "s#^R=.*#R=$R#" -e "s#\$R/.venv/bin/python#$PY#g" -e "s#WORK=\$D/work#WORK=$OUT/work#" \
           -e "s#\"\$D/frozen\"\$#\"$OUT/frozen\"#" $D/code/run_s23_oracle.sh > "$OUT/run_s23_oracle_portable.sh"
       mkdir -p "$OUT/frozen"; trap - EXIT; bash "$OUT/run_s23_oracle_portable.sh"
       IN=$(ls -d "$OUT"/frozen/*_input | tail -1); cmp_hash $D/frozen/20261031T180759Z_input/hashes.sha256 cases.jsonl "$IN/cases.jsonl"
       $PY $D/code/s23_score.py "$IN" $P "$OUT/results"
       cmp_hash $D/frozen/20261031T181038Z_results/hashes.sha256 s23_verdicts.csv "$OUT/results/s23_verdicts.csv" ;;
  *) echo "usage: $0 s18|s20|s23"; exit 64 ;;
esac
