"""S55J four-graph Community isolation layer for the remaining-260 scoring (derived from community_isolation_55f.py by asserted replacement).

Pure planning/routing/safety logic. Nothing here starts Docker or opens a Neo4j
connection unless a caller passes a driver. The frozen evaluator (project_ex.py,
score_predictions.py) is not modified: RoutedDriver presents the same
``driver.session(database=..., default_access_mode=...)`` surface so the frozen
``neo4j_executor`` can be reused unchanged.

SECURITY NOTE: Community has no database-enforced reader role. The controls here
(server-side read-only mode if it behaves as configured, loopback-only Bolt, resource
limits, query admission, integrity snapshots, fail-closed checks) are NOT equivalent
to Enterprise privilege enforcement. See GATE40_55F_COMMUNITY_SECURITY_AMENDMENT.md.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets

from project_ex import QueryRejected, read_only_query

IMAGE_TAG = "neo4j:5.15.0"
IMAGE_ID = "sha256:345d13bbe837f49280d6028dd405409d0fd6f7516921bd4a0b5776cafe49512c"
IMAGE_REPO_DIGEST = "neo4j@sha256:d9e2fb1ba398536e50d22ebc3d5d585baa086c1c0cf8e5b96bdc9e11e87e002a"
PHYSICAL_DATABASE = "neo4j"  # Community hosts exactly one standard database.
READ_TIMEOUT_S = 30
GRAPH_IDS = ("bloom", "er", "healthcare", "wwc")

# One graph per container; unique loopback ports (Bolt only, HTTP disabled/unpublished).
ENDPOINTS = {
    "bloom": {"container": "s55j-gate260-bloom", "datadir": "data_bloom", "port": 17711, "env_pw": "S55J_PW_BLOOM"},
    "er": {"container": "s55j-gate260-er", "datadir": "data_er", "port": 17712, "env_pw": "S55J_PW_ER"},
    "wwc": {"container": "s55j-gate260-wwc", "datadir": "data_wwc", "port": 17713, "env_pw": "S55J_PW_WWC"},
    "healthcare": {"container": "s55j-gate260-health", "datadir": "data_health", "port": 17714, "env_pw": "S55J_PW_HEALTH"},
}
LOOPBACK = "127.0.0.1"
TRACK = Path(__file__).resolve().parents[1]
RUNTIME = TRACK / "runtime_55j_scoring"          # all runtime state lives under the repository root
CRED_FILE = RUNTIME / ".credentials.env"  # 0600; excluded from git and from the evidence package


def validate_endpoints(endpoints=ENDPOINTS):
    """Distinct containers/volumes/ports/password variables; exact graph set."""
    if set(endpoints) != set(GRAPH_IDS):
        raise ValueError("endpoint graph set differs from frozen graphs")
    for key in ("container", "datadir", "port", "env_pw"):
        values = [endpoints[g][key] for g in GRAPH_IDS]
        if len(set(values)) != len(values):
            raise ValueError("endpoint collision on " + key)
    return endpoints


def server_environment(password_env_value_placeholder="NEO4J_AUTH"):
    """Server settings (names follow the Docker env mapping: '.'->'_', '_'->'__').

    Which of these Community 5.15 honours is UNVERIFIED until the live gate.
    """
    return {
        "NEO4J_server_databases_default__to__read__only": "true",
        "NEO4J_server_databases_read__only": PHYSICAL_DATABASE,
        "NEO4J_server_http_enabled": "false",
        "NEO4J_server_https_enabled": "false",
        "NEO4J_server_bolt_listen__address": "0.0.0.0:7687",  # container-internal; published to loopback only
        "NEO4J_dbms_security_procedures_allowlist": "dbms.components",
        "NEO4J_dbms_security_allow__csv__import__from__file__urls": "false",
        "NEO4J_db_transaction_timeout": "%ds" % READ_TIMEOUT_S,
        "NEO4J_db_memory_transaction_max": "256m",
        "NEO4J_dbms_memory_transaction_total_max": "512m",
        "NEO4J_server_memory_heap_initial__size": "384m",
        "NEO4J_server_memory_heap_max__size": "384m",
        "NEO4J_server_memory_pagecache_size": "128m",
        "NEO4J_dbms_security_auth__enabled": "true",
    }


def run_argv(graph, endpoints=ENDPOINTS):
    """docker run argv for one server container (never executed here)."""
    e = endpoints[graph]
    argv = ["docker", "run", "--detach", "--pull=never", "--name", e["container"],
            "--publish", "%s:%d:7687" % (LOOPBACK, e["port"]),
            "--memory=1g", "--memory-swap=1g", "--cpus=1", "--pids-limit=512",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--user", "7474:7474",  # image entrypoint skips chown/gosu when non-root
            "--volume", str(RUNTIME / e["datadir"]) + ":/data",
            "--env", "NEO4J_AUTH"]
    for key, value in server_environment().items():
        argv += ["--env", "%s=%s" % (key, value)]
    return argv + [IMAGE_ID]


def load_argv(graph, staged_dir, endpoints=ENDPOINTS):
    """One-off offline restore into this graph's own fresh volume (never executed here)."""
    e = endpoints[graph]
    return ["docker", "run", "--rm", "--pull=never", "--network=none",
            "--volume", str(RUNTIME / e["datadir"]) + ":/data", "--volume", str(staged_dir) + ":/dumps:ro",
            IMAGE_ID, "neo4j-admin", "database", "load", PHYSICAL_DATABASE, "--from-path=/dumps"]


def check_plan_security(argvs):
    """Static assertions over generated commands (offline test target)."""
    problems = []
    for argv in argvs:
        text = " ".join(argv)
        if argv[:3] == ["docker", "run", "--detach"] or "--detach" in argv:
            pubs = [argv[i + 1] for i, a in enumerate(argv) if a == "--publish"]
            if len(pubs) != 1 or not pubs[0].startswith(LOOPBACK + ":") or not pubs[0].endswith(":7687"):
                problems.append("publish not a single loopback Bolt port")
            if any(x.split(":")[-1] in ("7474", "7473") for x in pubs):
                problems.append("HTTP port referenced")
            if "--user" not in argv:
                problems.append("missing --user")
            for need in ("--cap-drop=ALL", "--security-opt=no-new-privileges", "--pull=never"):
                if need not in argv:
                    problems.append("missing " + need)
            if IMAGE_ID not in argv:
                problems.append("image not pinned by ID")
            if any(a.startswith("NEO4J_AUTH=") for a in argv):
                problems.append("password literal in argv")
        if "load" in argv and "--network=none" not in argv:
            problems.append("restore container has network")
    return problems


def load_credentials(create=False):
    """Per-container passwords from the environment, else the project-local 0600 file.

    Never printed. create=True (provisioning only) writes new random values once and
    refuses to overwrite an existing file.
    """
    names = [ENDPOINTS[g]["env_pw"] for g in GRAPH_IDS]
    if all(os.environ.get(n) for n in names):
        out = {n: os.environ[n] for n in names}
    elif CRED_FILE.is_file():
        if CRED_FILE.stat().st_mode & 0o077:
            raise PermissionError("credentials file permissions too open")
        out = dict(l.split("=", 1) for l in CRED_FILE.read_text().splitlines() if "=" in l)
    elif create:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        out = {n: secrets.token_urlsafe(24) for n in names}
        fd = os.open(CRED_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write("".join("%s=%s\n" % kv for kv in out.items()))
    else:
        raise ValueError("no credentials available")
    if set(names) - set(out) or len({out[n] for n in names}) != 4 or any(len(out[n]) < 16 for n in names):
        raise ValueError("credentials must be 4 distinct values of length >= 16")
    return {g: out[ENDPOINTS[g]["env_pw"]] for g in GRAPH_IDS}


# ---- query admission -------------------------------------------------------

_EXTRA = re.compile(r"\b(gds|apoc|dbms|jwt)\s*\.", re.I)


def admit(query):
    """Frozen read_only_query() first; only adds namespace rejections on top.

    Does not alter result semantics: anything it rejects was already rejected, or
    needs a plugin namespace that the server does not load.
    """
    read_only_query(query)
    if _EXTRA.search(re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", " ", query)):
        raise QueryRejected("plugin/system namespace")
    return query


class _Tx:
    def __init__(self, tx):
        self._tx = tx

    def run(self, query, *a, **kw):
        admit(query)
        return self._tx.run(query, *a, **kw)

    def rollback(self):
        return self._tx.rollback()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._tx.__exit__(*exc)


class _Session:
    def __init__(self, session):
        self._s = session

    def begin_transaction(self, **kw):
        return _Tx(self._s.begin_transaction(**kw))

    def __enter__(self):
        self._s.__enter__()
        return self

    def __exit__(self, *exc):
        return self._s.__exit__(*exc)


class RoutedDriver:
    """Maps frozen logical database names (s55er, ...) to one driver per container.

    Scoring sessions are READ-mode only and every transaction.run() passes admit().
    Unknown logical names, a missing driver, or an unverified graph raise (no fallback).
    """

    def __init__(self, drivers, logical_routes, verified=None):
        if set(drivers) != set(GRAPH_IDS) or set(logical_routes) != set(GRAPH_IDS):
            raise ValueError("need exactly four drivers/routes")
        if len(set(logical_routes.values())) != 4:
            raise ValueError("two graphs alias one logical database")
        self._by_logical = {logical_routes[g]: (g, drivers[g]) for g in GRAPH_IDS}
        self._verified = set(verified) if verified is not None else set()

    def mark_verified(self, graph):
        self._verified.add(graph)

    def session(self, database=None, default_access_mode="READ", **kw):
        if default_access_mode != "READ":
            raise PermissionError("scoring sessions must be READ")
        if database not in self._by_logical:
            raise ValueError("unknown logical database: %r" % (database,))
        graph, driver = self._by_logical[database]
        if graph not in self._verified:
            raise PermissionError("graph %s has not passed preflight identity checks" % graph)
        return _Session(driver.session(database=PHYSICAL_DATABASE, default_access_mode="READ", **kw))


# ---- stable content snapshot (no elementId) --------------------------------

def stable_snapshot(driver, timeout=READ_TIMEOUT_S):
    """Content hash independent of internal IDs; used for before/after integrity.

    Relationship endpoints are identified by (labels, properties) signatures, so
    two restores of the same dump should agree even if elementId differs.
    """
    def dump(v):
        return json.dumps(v, sort_keys=True, default=str)
    with driver.session(database=PHYSICAL_DATABASE, default_access_mode="READ") as s:
        with s.begin_transaction(timeout=timeout) as tx:
            nodes = tx.run("MATCH (n) RETURN labels(n) AS l, properties(n) AS p").data()
            rels = tx.run("MATCH (a)-[r]->(b) RETURN type(r) AS t, properties(r) AS p, "
                          "labels(a) AS al, properties(a) AS ap, labels(b) AS bl, properties(b) AS bp").data()
            tx.rollback()
    blob = json.dumps(sorted(dump(x) for x in nodes) + ["--"] + sorted(dump(x) for x in rels))
    return {"nodes": len(nodes), "relationships": len(rels),
            "stable_sha256": hashlib.sha256(blob.encode()).hexdigest()}


def assert_unchanged(before, after):
    for g in GRAPH_IDS:
        if before[g] != after[g]:
            raise RuntimeError("graph %s changed during scoring: fail closed" % g)
