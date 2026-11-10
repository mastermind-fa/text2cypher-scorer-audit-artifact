"""S55J preflight/scoring library: functions copied from gate40_workflow_55f.py (cut before main) by derive_55j_modules.py;
the four-graph set comes from community_isolation_55j."""
import json, os
from gate40_workflow_55d import fingerprint
from project_ex import neo4j_executor
from score_predictions import score_rows
import community_isolation_55j as iso

DENIAL_CODES = {"Neo.ClientError.General.ForbiddenOnReadOnlyDatabase",
                "Neo.ClientError.Security.Forbidden",
                "Neo.ClientError.General.WriteOnReadOnlyAccessDatabase"}
MESSAGE_REQUIRED = {"Neo.ClientError.General.WriteOnReadOnlyAccessDatabase": "read-only mode"}


def connect(endpoints=iso.ENDPOINTS):
    from neo4j import GraphDatabase
    drivers = {}
    pws = iso.load_credentials()
    for g in iso.GRAPH_IDS:
        pw = pws[g]
        drivers[g] = GraphDatabase.driver("bolt://%s:%d" % (iso.LOOPBACK, endpoints[g]["port"]), auth=("neo4j", pw))
    return drivers


def preflight(drivers, manifest, *, test_denial, neo4j_error=Exception):
    """Per-container identity, edition/version, frozen fingerprint, stable snapshot, write denial."""
    report, snapshots = {}, {}
    for g in iso.GRAPH_IDS:
        d = drivers[g]
        with d.session(database=iso.PHYSICAL_DATABASE, default_access_mode="READ") as s:
            comp = s.run("CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition").single()
        if comp is None or str(comp["edition"]).lower() != "community" or "5.15.0" not in comp["versions"]:
            raise ValueError("server edition/version mismatch: " + g)
        actual = fingerprint(d, iso.PHYSICAL_DATABASE)
        expected = manifest["graphs"][g]["fingerprint"]
        # Owner-approved identity rule S55G-ID-v1 (fixed before any score): exact equality of
        # node/relationship counts and label/type censuses. The frozen elementId-based SHA
        # cannot reproduce on a fresh instance (elementId embeds a per-database UUID); its
        # mismatch is retained and reported, never hidden.
        for key in ("nodes", "relationships", "label_counts", "rel_type_counts"):
            if actual[key] != expected[key]:
                raise ValueError("graph identity mismatch on %s: %s" % (key, g))
        snapshots[g] = iso.stable_snapshot(d)
        report[g] = {"container": iso.ENDPOINTS[g]["container"], "port": iso.ENDPOINTS[g]["port"],
                     "versions": comp["versions"], "edition": comp["edition"],
                     "frozen_fingerprint": actual, "stable_snapshot": snapshots[g],
                     "identity_rule": "S55G-ID-v1",
                     "frozen_elementid_sha_match": actual["sha256"] == expected["sha256"],
                     "frozen_elementid_sha_expected": expected["sha256"]}
        if test_denial:
            denied = False
            with d.session(database=iso.PHYSICAL_DATABASE, default_access_mode="WRITE") as s:
                with s.begin_transaction(timeout=iso.READ_TIMEOUT_S) as tx:
                    try:
                        tx.run("CREATE (:S55PermissionProbe)").consume()
                    except neo4j_error as exc:
                        code = getattr(exc, "code", None)
                        if code not in DENIAL_CODES:
                            raise ValueError("unexpected write-probe error code %r: %s" % (code, g))
                        need = MESSAGE_REQUIRED.get(code)
                        if need and need not in str(getattr(exc, "message", "")):
                            raise ValueError("write-probe message lacks %r: %s" % (need, g))
                        denied = True
                        report[g]["write_denial_code"] = code
                        report[g]["write_denial_message"] = str(getattr(exc, "message", ""))
                    finally:
                        tx.rollback()
            if not denied:
                raise ValueError("server accepted a write probe: " + g)
            report[g]["write_denied"] = True
    return report, snapshots


def run_scoring(packet, predictions, references, drivers, routes, snapshots_before):
    routed = iso.RoutedDriver(drivers, routes, verified=set(iso.GRAPH_IDS))
    traces, project_rows = score_rows(packet, predictions, references, neo4j_executor(routed, routes))
    after = {g: iso.stable_snapshot(drivers[g]) for g in iso.GRAPH_IDS}
    iso.assert_unchanged(snapshots_before, after)  # raises -> no outputs are written
    return traces, project_rows, after


