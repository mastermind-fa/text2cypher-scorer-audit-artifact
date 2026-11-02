#!/usr/bin/env bash
# study S23 EXECUTION BOUNDARY 2 (owner approval required): scores the FROZEN S23 input ONCE with the seven frozen
# primary scorers (+2 secondary, context only) through the frozen S14 runner / S13 adapters, then applies the frozen
# replication rubric. Offline (network blocked inside the runner), CPU only, no API, $0. No Neo4j needed.
set -euo pipefail
R="$(cd "$(dirname "$0")/../../../.." && pwd)"
D=$R/studies/native_mind_the_query/mind_the_query_replication
PRE=$(ls -d "$D"/frozen/*_preregistration | tail -1)
IN=$(ls -d "$D"/frozen/*_input | tail -1)
OUT=$D/frozen/$(date -u +%Y%m%dT%H%M%SZ)_results
for c in cypherturn cypherbench gqlbench tugraph_driver pipecypher cypherlens cyspider neo4jlabs_text2cypher; do
  test -z "$(git -C $R/external/$c status --porcelain)" || { echo "STOP: external/$c checkout not clean"; exit 4; }
done
time PYTHONDONTWRITEBYTECODE=1 $R/.venv/bin/python $D/code/s23_score.py "$IN" "$PRE" "$OUT"
