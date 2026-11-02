#!/usr/bin/env bash
# study S23 EXECUTION BOUNDARY 1 (owner approval required). Starts an ISOLATED throwaway Neo4j 5.15.0 container
# (image already used in study S18/20; port 17689; a throwaway docker volume removed on exit), loads the five pinned
# Mind the Query dumps into it ONE AT A TIME (neo4j-admin database load into the container's 'neo4j' database),
# runs the read-only oracle on the PREREGISTERED candidates, and freezes the input package. NO scorer is run.
# Mutates only the throwaway container/volume; the project's own graphs are not touched. CPU only, no API, $0.
# Docker Desktop must be running.
set -euo pipefail
R="$(cd "$(dirname "$0")/../../../.." && pwd)"
D=$R/studies/native_mind_the_query/mind_the_query_replication
MTQ=$R/external/mind_the_query
IMG=neo4j:5.15.0; NAME=s23-mtq-neo4j; VOL=s23-mtq-data; PW=s23-local-only; PORT=17689
PRE=$(ls -d "$D"/frozen/*_preregistration | tail -1)
CAND=$PRE/candidates.jsonl
WORK=$D/work/oracle_$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$WORK"
STAGE=$(mktemp -d)
cleanup() { docker rm -f $NAME >/dev/null 2>&1 || true; docker volume rm $VOL >/dev/null 2>&1 || true; rm -rf "$STAGE"; }
trap cleanup EXIT
dump_of() { case $1 in bloom) echo bloom-50.dump;; covid) echo contact-tracing-50.dump;;
  er) echo entity-resolution-50.dump;; healthcare) echo healthcare-analytics-50.dump;; wwc) echo wwc2019-50.dump;; esac; }

start_server() {
  docker run -d --name $NAME -p $PORT:7687 -e NEO4J_AUTH=neo4j/$PW -v $VOL:/data $IMG >/dev/null
  for i in $(seq 1 90); do
    docker exec $NAME cypher-shell -u neo4j -p $PW "MATCH (n) RETURN count(n) AS n" >/dev/null 2>&1 && return 0
    sleep 2
  done
  docker logs $NAME > "$WORK/server_start_failure.log" 2>&1 || true
  echo "STOP: database did not come online (see $WORK/server_start_failure.log)"; exit 2
}
stop_server() { docker stop $NAME >/dev/null; docker rm $NAME >/dev/null; }

docker volume create $VOL >/dev/null
start_server; stop_server                     # initialise the throwaway volume (auth, ownership)
T0=$(date +%s)
for g in bloom covid er healthcare wwc; do
  mkdir -p "$STAGE/$g"; cp "$MTQ/Datasets/$(dump_of $g)" "$STAGE/$g/neo4j.dump"
  t=$(date +%s)
  docker run --rm -v $VOL:/data -v "$STAGE/$g":/dumps:ro $IMG \
    neo4j-admin database load neo4j --from-path=/dumps --overwrite-destination=true > "$WORK/$g.load.log" 2>&1 \
    || { echo "STOP: load failed for $g (see $WORK/$g.load.log)"; cat "$WORK/$g.load.log"; exit 3; }
  start_server
  echo "{\"graph\":\"$g\",\"load_and_start_seconds\":$(( $(date +%s) - t ))}" >> "$WORK/timings.jsonl"
  t=$(date +%s)
  PYTHONDONTWRITEBYTECODE=1 $R/.venv/bin/python $D/code/s23_oracle.py eval-graph "$CAND" $g \
    bolt://localhost:$PORT neo4j $PW "$WORK" "$MTQ/Datasets/$(dump_of $g)"
  echo "{\"graph\":\"$g\",\"oracle_seconds\":$(( $(date +%s) - t ))}" >> "$WORK/timings.jsonl"
  stop_server
done
echo "{\"total_seconds\":$(( $(date +%s) - T0 ))}" >> "$WORK/timings.jsonl"
PYTHONDONTWRITEBYTECODE=1 $R/.venv/bin/python $D/code/s23_oracle.py freeze "$CAND" "$WORK" "$PRE" "$D/frozen"
