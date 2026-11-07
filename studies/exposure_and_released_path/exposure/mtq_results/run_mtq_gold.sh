#!/usr/bin/env bash
# Throwaway Neo4j 5.15.0 container (data bind-mounted under the project root); loads
# the five pinned Mind the Query dumps one at a time and runs every manual test-split gold query once, read-only.
# Mutates only a throwaway data directory under the project root (deleted on exit). CPU only, no API, no external quota, $0. ~5 min. All files stay in the project.
set -euo pipefail
R="$(cd "$(dirname "$0")/../../../.." && pwd)"
D="$(cd "$(dirname "$0")" && pwd)"
MTQ="$R/external/mind_the_query"
IMG=neo4j:5.15.0; NAME=s49-mtq-neo4j; PW=s49-local-only; PORT=17690
STAGE="$D/scratch/mtq_stage"; DATA="$D/scratch/neo4j_data"; OUT="$D/mtq_gold_results.jsonl"   # all state under the project root
mkdir -p "$STAGE" "$DATA"; : > "$OUT"
cleanup() { docker rm -f $NAME >/dev/null 2>&1 || true; rm -rf "$STAGE" "$DATA"; }
trap cleanup EXIT
dump_of() { case $1 in bloom) echo bloom-50.dump;; covid) echo contact-tracing-50.dump;;
  er) echo entity-resolution-50.dump;; healthcare) echo healthcare-analytics-50.dump;; wwc) echo wwc2019-50.dump;; esac; }
start_server() {
  docker run -d --name $NAME -p 127.0.0.1:$PORT:7687 -e NEO4J_AUTH=neo4j/$PW -v "$DATA":/data $IMG >/dev/null
  for i in $(seq 1 90); do docker exec $NAME cypher-shell -u neo4j -p $PW "RETURN 1" >/dev/null 2>&1 && return 0; sleep 2; done
  echo "STOP: server did not start"; exit 2
}
stop_server() { docker stop $NAME >/dev/null; docker rm $NAME >/dev/null; }
start_server; stop_server
for g in bloom covid er healthcare wwc; do
  mkdir -p "$STAGE/$g"; cp "$MTQ/Datasets/$(dump_of $g)" "$STAGE/$g/neo4j.dump"
  docker run --rm -v "$DATA":/data -v "$STAGE/$g":/dumps:ro $IMG \
    neo4j-admin database load neo4j --from-path=/dumps --overwrite-destination=true > "$D/$g.load.log" 2>&1
  start_server
  "${PYTHON:-python3}" "$D/execute_mtq_gold.py" $g bolt://localhost:$PORT neo4j $PW "$OUT"
  stop_server
done
(cd "$D" && shasum -a 256 mtq_gold_results.jsonl > mtq_gold_results.sha256)
echo "done: $(wc -l < "$OUT") rows -> $OUT"
