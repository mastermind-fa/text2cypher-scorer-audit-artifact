"""Proposed S55 project execution metric. No benchmark-official status is claimed.

The evaluator accepts an injected read-only executor so all result logic is testable
without a database. A Neo4j executor is supplied separately below.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import json
import math
import re

VERSION = "s55-project-ex-v1-proposed"
MAX_ROWS = 10000
TIMEOUT_MS = 30000


class UnsupportedValue(Exception):
    pass


class QueryRejected(Exception):
    pass


class ResultLimit(Exception):
    pass


def read_only_query(query: str) -> None:
    """Conservative gate; DB read-only privileges are still mandatory."""
    if not isinstance(query, str) or not query.strip():
        raise QueryRejected("empty query")
    # Mask quoted literals and escaped backtick identifiers before keyword checks.
    # Comments and unterminated literals are refused. DB permissions remain mandatory.
    masked=[];i=0
    while i<len(query):
        c=query[i]
        if c in ("'",'"','`'):
            quote=c;masked.append(' ');i+=1;closed=False
            while i<len(query):
                if query[i]=='\\' and quote!='`':
                    masked.extend(' ' for _ in query[i:i+2]);i+=2;continue
                if query[i]==quote:
                    if i+1<len(query) and query[i+1]==quote:
                        masked.extend((' ',' '));i+=2;continue
                    masked.append(' ');i+=1;closed=True;break
                masked.append(' ');i+=1
            if not closed:raise QueryRejected("unterminated literal or identifier")
            continue
        masked.append(c);i+=1
    code=''.join(masked)
    if re.search(r"//|/\*|\*/|;|\b(CALL|CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD|FOREACH|USE|SHOW|GRANT|DENY|REVOKE|ALTER|START|STOP|TERMINATE|APOC|DBMS)\b", code, re.I):
        raise QueryRejected("disallowed construct")
    if not re.match(r"^\s*(MATCH|OPTIONAL\s+MATCH|WITH|UNWIND|RETURN)\b", code, re.I):
        raise QueryRejected("disallowed opening clause")
    if not re.search(r"\bRETURN\b", code, re.I):
        raise QueryRejected("missing RETURN")


def normal(value):
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("num", Decimal(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise UnsupportedValue("nonfinite float")
        return ("num", Decimal(str(value)))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise UnsupportedValue("nonfinite decimal")
        return ("num", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, (datetime, date, time)):
        return (type(value).__name__, value.isoformat())
    if isinstance(value, (list, tuple)):
        return ("list", tuple(normal(v) for v in value))
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise UnsupportedValue("non-string map key")
        return ("map", tuple(sorted((k, normal(v)) for k, v in value.items())))
    raise UnsupportedValue(type(value).__name__)


def equal_value(a, b):
    if a[0] != b[0]:
        return False
    if a[0] == "num":
        return abs(a[1] - b[1]) <= Decimal("0.000000001")
    if a[0] == "list":
        return len(a[1]) == len(b[1]) and all(equal_value(x, y) for x, y in zip(a[1], b[1]))
    if a[0] == "map":
        return len(a[1]) == len(b[1]) and all(x[0] == y[0] and equal_value(x[1], y[1]) for x, y in zip(a[1], b[1]))
    return a == b


def compare_results(reference, prediction):
    """Sides have columns and rows. Alias names ignored; column positions retained.

    Row order ignored, row multiplicity retained, numeric tolerance absolute 1e-9.
    A maximum-cardinality matching avoids greedy tolerance artifacts.
    """
    rc, pc = reference["columns"], prediction["columns"]
    rr, pr = reference["rows"], prediction["rows"]
    if len(rc) != len(pc) or len(rr) != len(pr):
        return False
    if len(rr) > MAX_ROWS or len(pr) > MAX_ROWS:
        raise ResultLimit("too many rows")
    if len(set(rc)) != len(rc) or len(set(pc)) != len(pc):
        raise UnsupportedValue("duplicate column names")
    if any(len(r) != len(rc) for r in rr) or any(len(r) != len(pc) for r in pr):
        raise UnsupportedValue("row arity")
    left = [tuple(normal(v) for v in row) for row in rr]
    right = [tuple(normal(v) for v in row) for row in pr]
    edges = [[j for j, y in enumerate(right) if all(equal_value(xv, yv) for xv, yv in zip(x, y))]
             for x in left]
    matched = {}
    def augment(i, seen):
        for j in edges[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in matched or augment(matched[j], seen):
                matched[j] = i
                return True
        return False
    return all(augment(i, set()) for i in range(len(left)))


def evaluate(reference_query, predicted_query, graph, executor):
    """Executor(query, graph, timeout_ms, max_rows) returns columns/rows."""
    result = {"metric": VERSION, "graph": graph, "reference_query": reference_query,
              "predicted_query": predicted_query, "verdict": None, "status": None,
              "reference": None, "prediction": None, "errors": {}}
    for side, query in (("reference", reference_query), ("prediction", predicted_query)):
        try:
            read_only_query(query)
            result[side] = executor(query, graph, TIMEOUT_MS, MAX_ROWS)
            if len(result[side]["rows"]) > MAX_ROWS:
                raise ResultLimit("too many rows")
            for row in result[side]["rows"]:
                for v in row:
                    normal(v)
        except Exception as exc:
            kind = "unsupported" if isinstance(exc, (UnsupportedValue, ResultLimit)) else "execution_error"
            result["errors"][side] = {"kind": kind, "type": type(exc).__name__, "message": str(exc)[:300]}
    if "reference" in result["errors"]:
        result["status"] = "invalid_reference"
    elif "prediction" in result["errors"]:
        result["status"] = result["errors"]["prediction"]["kind"]
        if result["status"] == "execution_error":
            result["verdict"] = 0
    else:
        try:
            result["verdict"] = int(compare_results(result["reference"], result["prediction"]))
            result["status"] = "scored"
        except (UnsupportedValue, ResultLimit) as exc:
            result["status"] = "unsupported"
            result["errors"]["comparison"] = {"type": type(exc).__name__, "message": str(exc)}
    return result


def neo4j_executor(driver, databases):
    """Use a dedicated read-only Neo4j account; databases maps frozen graph IDs."""
    def run(query, graph, timeout_ms, max_rows):
        if graph not in databases:
            raise ValueError("unknown graph")
        with driver.session(database=databases[graph], default_access_mode="READ") as session:
            with session.begin_transaction(timeout=timeout_ms / 1000) as tx:
                res = tx.run(query)
                columns = list(res.keys())
                rows = []
                for rec in res:
                    rows.append(list(rec.values()))
                    if len(rows) > max_rows:
                        raise ResultLimit("too many rows")
                tx.rollback()
                return {"columns": columns, "rows": rows}
    return run
