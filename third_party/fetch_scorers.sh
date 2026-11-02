#!/usr/bin/env bash
# Fetch the audited scorer repositories at their pinned commits into external/<local_dir> (sparse, as audited) and
# verify each scorer file's SHA-256 against external/EXTERNAL_PINS.json. Public GitHub only; no credentials.
set -euo pipefail
cd "$(dirname "$0")/.."
fetch() {  # local_dir url commit sparse-paths...
  local d=$1 url=$2 c=$3; shift 3
  [ -d "external/$d/.git" ] && { echo "exists: external/$d"; return; }
  git clone -q --filter=blob:none --no-checkout "$url" "external/$d"
  git -C "external/$d" sparse-checkout init --no-cone
  git -C "external/$d" sparse-checkout set "$@"
  git -C "external/$d" checkout -q "$c"
  echo "fetched $d @ $(git -C external/$d rev-parse --short HEAD)"
}
fetch cypherturn https://github.com/BarryQ/CypherTurn.git 9d9528e16c8fe2fb388b9daa4b43dcaa6f229612 /LICENSE\* /README\* /requirements\* /pyproject.toml /setup.py /graph_eval_utils/ /eval/ /data/ /docker/
fetch cypherbench https://github.com/megagonlabs/cypherbench.git 4cc727d29acc78f8cea7c4daa4e2705ddf293b8b /LICENSE\* /README\* /requirements\* /pyproject.toml /setup.py /cypherbench/metrics/ /cypherbench/neo4j_connector.py /cypherbench/__init__.py /cypherbench/schema.py /cypherbench/utils.py
fetch gqlbench https://github.com/qxssadf/GQLBench.git fb9d5a9be3ccc73ea9fe44c67a9b180eccedfad2 /LICENSE\* /README\* /requirements\* /Code/
fetch tugraph_driver https://github.com/ldbc/Text2GraphQuery-Driver.git ab296fab179e806cd3ad2e659e9f5dc61bd1af3e /LICENSE\* /README\* /requirements\* /pyproject.toml /setup.py /impl/evaluation/ /driver/
fetch pipecypher https://github.com/suraj-ranganath/PIPE-Cypher.git 0f127208746eb1035d95803348cc5cde36d47d7e /LICENSE\* /README\* /requirements\* /pyproject.toml /setup.py /pipecypher/
fetch cypherlens https://github.com/YasmeanMohammadi/cypherLenz.git ce6481941e78d12fcec974babf453891487ef17a /LICENSE\* /README\* /requirements\* /services/ /models/ /main.py /config/config_.yml
fetch cyspider https://github.com/22842219/SemanticParser4Graph.git 6cd5eff4aa37b40a2557d312f70ec0d576d8a6b1 /semantic_parser/LICENSE /semantic_parser/metrics/text2cypher/
fetch neo4jlabs_text2cypher https://github.com/neo4j-labs/text2cypher.git a8ed4d9480bcd4aa1b1a0b2e57aadd996afeaca2 /LICENSE\* /README\* /evaluations/
python3 - <<'PY'
import hashlib, json, sys
pins = json.load(open("external/EXTERNAL_PINS.json"))["repos"]; bad = 0
for r in pins:
    if not r.get("scorer_sha256"): continue
    f = r["scorer_file"].split(" ")[0]; h = hashlib.sha256(open(f"external/{r['local_dir']}/{f}", "rb").read()).hexdigest()
    ok = h == r["scorer_sha256"]; bad += not ok
    print(("OK  " if ok else "FAIL"), r["local_dir"], f)
sys.exit(1 if bad else 0)
PY
