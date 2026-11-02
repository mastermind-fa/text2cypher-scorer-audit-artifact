#!/usr/bin/env bash
# study S20 EXECUTION BOUNDARY (owner approval required): starts an ISOLATED throwaway Neo4j 5.15.0 container
# (CypherTurn's image version; port 17688, no volume, removed on stop), loads each CypherTurn graph into it in turn
# (mutating ONLY this throwaway container), runs the read-only oracle on reference + candidate queries and freezes the
# input package. NO scorer is run. The project's G0 graph is not touched. Free, CPU-only, no API.
# Docker Desktop must be running; neo4j:5.15.0 is already pulled from study S18 (otherwise ~0.5 GB, free).
set -euo pipefail
R="$(cd "$(dirname "$0")/../../../.." && pwd)"
D=$R/studies/native_cypherturn_stress/native_equivalence_stress
docker run -d --rm --name s20-cypherturn-neo4j -p 17688:7687 -e NEO4J_AUTH=neo4j/s20-local-only neo4j:5.15.0
trap 'docker stop s20-cypherturn-neo4j >/dev/null 2>&1 || true' EXIT
until docker exec s20-cypherturn-neo4j cypher-shell -u neo4j -p s20-local-only "RETURN 1" >/dev/null 2>&1; do sleep 2; done
PYTHONDONTWRITEBYTECODE=1 python3 $D/code/s20_rules.py $R/external/cypherturn \
  $R/studies/native_cypherturn_validation/native_cypher/frozen/20261030T083217Z_native_cypher_input/cases.jsonl $D/candidates/candidates.jsonl
PYTHONDONTWRITEBYTECODE=1 $R/.venv/bin/python $D/code/s20_oracle.py $D/candidates/candidates.jsonl $R/external/cypherturn \
  bolt://localhost:17688 neo4j s20-local-only $D/frozen
