# Third-party scorers and benchmarks

No third-party code or benchmark data is included in this repository.
- **`fetch_scorers.sh`:** fetches each audited scorer from its original repository at the pinned commit (sparse
  checkout into `external/`). It then checks each scorer file's SHA-256 against `external/EXTERNAL_PINS.json`.
- **`fetch_mind_the_query.sh`:** fetches the Mind the Query benchmark at its pinned commit and verifies the graph-dump
  hashes. The dumps are used locally and never redistributed.
- **`scorers.lock`:** a readable summary of the pins: name, source URL, commit, scorer file, expected SHA-256, licence
  where stated, and role.
- **`scorer_manifest.yaml`:** maps each scorer to the project adapter that runs it.

Licences are as stated by each upstream repository; several upstream repositories state none, which is why nothing is
redistributed.

The Text2GraphQuery-Driver pin uses its original address (`TuGraph-family/text2graphquery-driver`), which GitHub
redirects to the current canonical repository `ldbc/Text2GraphQuery-Driver`. The pinned commit is the same.
