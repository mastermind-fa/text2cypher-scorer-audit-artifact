#!/usr/bin/env bash
# Fetch Mind the Query (endeavorXx/Mind-the-Query @ec4054a1, Apache-2.0 repository) into external/mind_the_query.
# Sparse rules are set BEFORE the first checkout, so the repository's .env is never materialised. Verifies dump hashes.
# The graph dumps' own licence is unverified: they are used locally and never redistributed by this artifact.
set -euo pipefail
cd "$(dirname "$0")/.."
D=external/mind_the_query
[ -d $D/.git ] || {
  git clone -q --filter=blob:none --no-checkout https://github.com/endeavorXx/Mind-the-Query.git $D
  git -C $D sparse-checkout init --no-cone
  git -C $D sparse-checkout set /ReadMe.md /LICENSE /db_schema.jsonl /Datasets/bloom-50.dump /Datasets/contact-tracing-50.dump \
    /Datasets/entity-resolution-50.dump /Datasets/healthcare-analytics-50.dump /Datasets/wwc2019-50.dump '/Train_Test_Splits/Manual/' \
    /Train_Test_Splits/split_statistics.txt /Manually_Validated_Datasets/annotation_protocol.txt
  git -C $D checkout -q ec4054a1b7df7e6310efa95c56bb6e7cebc4d161; }
[ -e $D/.env ] && { echo "STOP: .env present"; exit 1; }
python3 - <<'PY'
import hashlib, json, sys
pre = json.load(open("studies/native_mind_the_query/mind_the_query_replication/frozen/20261031T175346Z_preregistration/preregistration.json"))["source"]
bad = 0
for g, f in pre["graphs_to_dumps"].items():
    ok = hashlib.sha256(open(f"external/mind_the_query/Datasets/{f}", "rb").read()).hexdigest() == pre["dump_sha256"][g]; bad += not ok
    print(("OK  " if ok else "FAIL"), f)
for f, h in pre["manual_test_files_sha256"].items():
    bad += hashlib.sha256(open(f"external/mind_the_query/{f}", "rb").read()).hexdigest() != h
print("test-split files:", "OK" if not bad else "FAIL"); sys.exit(1 if bad else 0)
PY
