#!/usr/bin/env bash
# study S18 EXECUTION BOUNDARY (owner approval required): starts an ISOLATED throwaway Neo4j 5.15.0 container
# (CypherTurn's own image version; port 17687, no volume, removed on stop), loads each CypherTurn graph into it in turn,
# runs the oracle (read-only queries on gold + rewrites) and freezes the input package. The project's G0 graph is not
# touched. Free, CPU-only, no API. Docker Desktop must be running.
set -euo pipefail
R="$(cd "$(dirname "$0")/../../../.." && pwd)"
D=$R/studies/native_cypherturn_validation/native_cypher
docker run -d --rm --name s18-cypherturn-neo4j -p 17687:7687 -e NEO4J_AUTH=neo4j/s18-local-only neo4j:5.15.0
until docker exec s18-cypherturn-neo4j cypher-shell -u neo4j -p s18-local-only "RETURN 1" >/dev/null 2>&1; do sleep 2; done
mkdir -p $D/candidates $D/frozen
python3 $D/code/s18_rewrite.py $R/external/cypherturn $D/candidates/candidates.jsonl
PYTHONDONTWRITEBYTECODE=1 $R/.venv/bin/python $D/code/s18_oracle.py $D/candidates/candidates.jsonl $R/external/cypherturn \
  bolt://localhost:17687 neo4j s18-local-only $D/frozen
docker stop s18-cypherturn-neo4j
