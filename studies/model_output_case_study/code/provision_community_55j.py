"""Owner-gated S55J provisioning: four separate Neo4j 5.15 Community containers (derived from provision_community_55f.py).

plan  : read-only; verifies dump hashes, image identity (docker inspect), endpoints
        and prints the exact commands. Starts nothing.
execute: requires --owner-authorized-deployment AND --owner-authorized-security-amendment.
        Creates/restores ONLY the six named S55F resources. Refuses existing resources
        or busy ports; never deletes anything; retains resources on failure.
No licence acceptance is needed for Community (GPLv3 server); none is set here.
Runtime state (bind mounts, staging, credentials) is project-local under runtime_55g/; no Docker named volumes.
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

import hashlib
import community_isolation_55j as iso
GRAPH_MANIFEST = iso.TRACK / "GATE260_FOUR_GRAPH_MAPPING.json"
GRAPH_MANIFEST_SHA = "41e5fa12e641cbcb66cc772c02e118b0295447a10f33ea973bc34fdb026abd6b"
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()

MIN_PW = 16


def command(argv, *, env=None, allow_fail=False):
    proc = subprocess.run(argv, text=True, capture_output=True, env=env)
    if proc.returncode and not allow_fail:
        err = proc.stderr or ""
        for g in iso.GRAPH_IDS:
            secret = os.environ.get(iso.ENDPOINTS[g]["env_pw"])
            if secret:
                err = err.replace(secret, "[REDACTED]")
        raise RuntimeError("command failed: %s stderr=%s" % (" ".join(argv[:4]), err[-800:]))
    return proc


def image_preflight():
    items = json.loads(command(["docker", "image", "inspect", iso.IMAGE_ID]).stdout)
    if len(items) != 1:
        raise ValueError("ambiguous image")
    it = items[0]
    env = dict(x.split("=", 1) for x in it["Config"]["Env"] if "=" in x)
    if (it["Id"] != iso.IMAGE_ID or it["Architecture"] != "arm64" or it["Os"] != "linux"
            or iso.IMAGE_REPO_DIGEST not in it.get("RepoDigests", [])
            or env.get("NEO4J_EDITION") != "community"
            or env.get("NEO4J_TARBALL") != "neo4j-community-5.15.0-unix.tar.gz"):
        raise ValueError("Community image identity drift")
    return {"image_id": it["Id"], "edition": env["NEO4J_EDITION"], "tarball": env["NEO4J_TARBALL"]}


def port_free(port):
    with socket.socket() as s:
        return s.connect_ex((iso.LOOPBACK, port)) != 0


def ensure_absent(endpoints=iso.ENDPOINTS):
    for g in iso.GRAPH_IDS:
        e = endpoints[g]
        if command(["docker", "container", "inspect", e["container"]], allow_fail=True).returncode == 0:
            raise ValueError("container exists, no reuse: " + e["container"])
        if (iso.RUNTIME / e["datadir"]).exists():
            raise ValueError("data directory exists, no reuse: " + e["datadir"])
        if not port_free(e["port"]):
            raise ValueError("port in use: %d" % e["port"])


def build_plan(dump_root):
    iso.validate_endpoints()
    if sha(GRAPH_MANIFEST) != GRAPH_MANIFEST_SHA:
        raise ValueError("graph mapping drift")
    manifest = json.loads(GRAPH_MANIFEST.read_text())
    if set(manifest["graphs"]) != set(iso.GRAPH_IDS):
        raise ValueError("graph set drift")
    for g in iso.GRAPH_IDS:
        item = manifest["graphs"][g]
        path = Path(dump_root) / item["dump_file"]
        if not path.is_file():
            raise ValueError("missing dump: " + g)
        if sha(path) != item["dump_sha256"]:
            raise ValueError("dump hash mismatch: " + g)
    return manifest


def passwords(create=False):
    return iso.load_credentials(create=create)


def wait_ready(port, pw, tries=90):
    from neo4j import GraphDatabase
    last = None
    for _ in range(tries):
        try:
            d = GraphDatabase.driver("bolt://%s:%d" % (iso.LOOPBACK, port), auth=("neo4j", pw))
            d.verify_connectivity()
            d.close()
            return
        except Exception as exc:
            last = exc
            time.sleep(2)
    raise RuntimeError("server not ready: " + type(last).__name__)


def execute(manifest, dump_root, *, deployment_ok=False, amendment_ok=False):
    if not (deployment_ok and amendment_ok):
        raise ValueError("deployment and security-amendment authorizations are both required")
    ensure_absent()
    image_preflight()
    stage_root = iso.RUNTIME / "staging"
    stage_root.mkdir(parents=True, exist_ok=True)
    pws = passwords(create=True)
    with tempfile.TemporaryDirectory(prefix="s55j-dumps-", dir=stage_root) as stage:
        for g in iso.GRAPH_IDS:  # each dump restored ONLY into its own volume
            e = iso.ENDPOINTS[g]
            item = manifest["graphs"][g]
            folder = Path(stage) / g
            folder.mkdir()
            shutil.copyfile(Path(dump_root) / item["dump_file"], folder / (iso.PHYSICAL_DATABASE + ".dump"))
            if sha(folder / (iso.PHYSICAL_DATABASE + ".dump")) != item["dump_sha256"]:
                raise ValueError("staged dump mismatch: " + g)
            (iso.RUNTIME / e["datadir"]).mkdir(parents=True)
            command(iso.load_argv(g, folder))
    for g in iso.GRAPH_IDS:
        env = dict(os.environ, NEO4J_AUTH="neo4j/" + pws[g])
        command(iso.run_argv(g), env=env)
    for g in iso.GRAPH_IDS:
        wait_ready(iso.ENDPOINTS[g]["port"], pws[g])
    print(json.dumps({"status": "PROVISIONED_UNVERIFIED", "containers": {g: iso.ENDPOINTS[g]["container"] for g in iso.GRAPH_IDS},
                      "next": "separately authorized live preflight; no Gate40 query executed"}))


def start_only(manifest):
    """Attempt-2 recovery: start servers on ALREADY RESTORED project-local data dirs.

    Used after attempt 1 restored all three stores but the containers exited on an
    entrypoint chown failure (cap-drop=ALL while root). Never re-restores or deletes.
    """
    for g in iso.GRAPH_IDS:
        e = iso.ENDPOINTS[g]
        if not (iso.RUNTIME / e["datadir"] / "databases" / iso.PHYSICAL_DATABASE).is_dir():
            raise ValueError("no restored store for " + g)
        if command(["docker", "container", "inspect", e["container"]], allow_fail=True).returncode == 0:
            raise ValueError("container exists, no reuse: " + e["container"])
        if not port_free(e["port"]):
            raise ValueError("port in use: %d" % e["port"])
    image_preflight()
    pws = passwords()
    for g in iso.GRAPH_IDS:
        command(iso.run_argv(g), env=dict(os.environ, NEO4J_AUTH="neo4j/" + pws[g]))
    for g in iso.GRAPH_IDS:
        wait_ready(iso.ENDPOINTS[g]["port"], pws[g])
    print(json.dumps({"status": "STARTED_UNVERIFIED", "next": "live preflight"}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("plan", "execute", "start-only"))
    p.add_argument("--dump-root", type=Path, required=True)
    p.add_argument("--owner-authorized-deployment", action="store_true")
    p.add_argument("--owner-authorized-security-amendment", action="store_true")
    a = p.parse_args()
    manifest = build_plan(a.dump_root)
    if a.mode == "plan":
        argvs = [iso.run_argv(g) for g in iso.GRAPH_IDS] + [iso.load_argv(g, "<staging>") for g in iso.GRAPH_IDS]
        problems = iso.check_plan_security(argvs)
        if problems:
            raise SystemExit("plan security check failed: " + "; ".join(problems))
        print(json.dumps({"status": "PLAN_ONLY", "image": iso.IMAGE_ID, "dumps_verified": True,
                          "endpoints": iso.ENDPOINTS, "commands": [" ".join(x) for x in argvs]}, indent=1))
        return
    if a.mode == "start-only":
        if not (a.owner_authorized_deployment and a.owner_authorized_security_amendment):
            raise SystemExit("authorization flags required")
        return start_only(manifest)
    execute(manifest, a.dump_root, deployment_ok=a.owner_authorized_deployment,
            amendment_ok=a.owner_authorized_security_amendment)


if __name__ == "__main__":
    main()
