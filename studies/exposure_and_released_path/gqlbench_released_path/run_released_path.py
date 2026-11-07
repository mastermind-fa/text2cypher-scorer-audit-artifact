"""Run GQLBench's unmodified Cypher scoring path (real neo4j driver + Result.to_df) on the S20 numeric-NULL case.

See PROTOCOL.md (frozen before execution). Read-only queries only; the graph is not loaded.
Usage: NEO4J_TEST_PASSWORD=... python run_released_path.py [path/to/S20 cases.jsonl]
"""
import contextlib
import io
import json
import os
import platform
import random
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CASES = None  # pass the rebuilt CypherTurn stress-suite cases.jsonl (CypherTurn content is not redistributed)
CASE_ID = "S20-69098610ca"
OUT = Path(__file__).resolve().parent / "results.json"


def stub_nebula():
    names = {"nebulagraph_python": ["NebulaClient", "SessionConfig", "SessionPoolConfig"],
             "nebulagraph_python.client": [], "nebulagraph_python.client._connection": ["ConnectionConfig"],
             "nebulagraph_python.data": ["HostAddress"]}
    for mod, attrs in names.items():
        m = types.ModuleType(mod)
        for a in attrs:
            setattr(m, a, type(a, (), {}))
        sys.modules.setdefault(mod, m)


def literal(v):
    if v is None:
        return "null"
    if isinstance(v, str):
        return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"
    return repr(v)


def unwind_query(rows, ordered=True, coalesce=False):
    body = ", ".join("[" + ", ".join(literal(x) for x in [i] + list(r)) + "]" for i, r in enumerate(rows))
    second = "coalesce(r[2], null)" if coalesce else "r[2]"
    order = " WITH r ORDER BY r[0]" if ordered else ""
    return f"UNWIND [{body}] AS r{order} RETURN r[1] AS name, {second} AS p_opt"


def main():
    import neo4j
    import numpy
    import pandas
    stub_nebula()
    sys.path.insert(0, str(ROOT / "external/gqlbench/Code"))
    sys.path.insert(0, str(ROOT / "external/gqlbench/Code/eval"))
    import execute_accuracy as ea
    ea.NEO4jUSERNAME = "neo4j"
    ea.NEO4jPASSWORD = os.environ["NEO4J_TEST_PASSWORD"]
    assert ea.GraphDatabase is neo4j.GraphDatabase  # the real driver, not a replay object

    cases = Path(sys.argv[1]) if len(sys.argv) > 1 else CASES  # artifact: the rebuilt S20 cases.jsonl
    case = next(json.loads(l) for l in cases.open() if json.loads(l)["case_id"] == CASE_ID)
    ref_rows = case["reference"]["rows"]
    assert ref_rows == case["prediction"]["rows"]
    no_null = [[n, 0 if v is None else v] for n, v in ref_rows]
    str_null = [[None if i in (1, 2, 3) else n, v] for i, (n, v) in enumerate(no_null)]

    # Probe: what the released materialisation produces for the flagship rows.
    drv = neo4j.GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", ea.NEO4jPASSWORD))
    df = drv.execute_query(neo4j.Query(unwind_query(ref_rows)), database_="neo4j",
                           result_transformer_=neo4j.Result.to_df)
    tuples = [tuple(row) for row in df.itertuples(index=False)]
    null_cells = [t[1] for t in tuples if t[1] != t[1]]
    probe = {"dtypes": {c: str(t) for c, t in df.dtypes.items()},
             "null_cell_python_types": sorted({type(x).__name__ for x in null_cells}),
             "null_cells": len(null_cells),
             "distinct_null_objects_one_side": len({id(x) for x in null_cells})}
    df2 = drv.execute_query(neo4j.Query(unwind_query(ref_rows, coalesce=True)), database_="neo4j",
                            result_transformer_=neo4j.Result.to_df)
    t2 = [tuple(row) for row in df2.itertuples(index=False)]
    a, b = tuples[1][1], t2[1][1]
    probe["cross_side_first_null"] = {"a_is_b": a is b, "a_eq_b": bool(a == b),
                                      "tuple_eq": tuples[1] == t2[1], "hash_a": hash(a), "hash_b": hash(b)}
    drv.close()

    runs = {
        "R1_flagship_ordered": (unwind_query(ref_rows), unwind_query(ref_rows, coalesce=True)),
        "R2_flagship_unordered": (unwind_query(ref_rows, ordered=False),
                                  unwind_query(ref_rows, ordered=False, coalesce=True)),
        "R3_control_no_null": (unwind_query(no_null), unwind_query(no_null, coalesce=True)),
        "R4_control_string_null": (unwind_query(str_null), unwind_query(str_null, coalesce=True)),
        "R5_identical_text": (unwind_query(ref_rows), unwind_query(ref_rows)),
    }
    results = {}
    for name, (ref, pred) in runs.items():
        random.seed(42)
        with contextlib.redirect_stdout(io.StringIO()):
            out = ea.execution_accuracy(pred, ref, "neo4j", "cypher", "neo4j")
        results[name] = {"verdict": repr(out[0]), "message": out[1], "accepted": bool(out[0] == 1),
                         "order_matters": "order by" in ref.lower()}

    record = {
        "case_id": CASE_ID, "protocol": "PROTOCOL.md",
        "environment": {"python": platform.python_version(), "neo4j_driver": neo4j.__version__,
                        "pandas": pandas.__version__, "numpy": numpy.__version__,
                        "neo4j_server": os.environ.get("NEO4J_SERVER_VERSION", "UNRECORDED")},
        "gqlbench_commit": "fb9d5a9be3ccc73ea9fe44c67a9b180eccedfad2",
        "probe": probe, "runs": results,
        "queries": {k: {"reference": v[0], "prediction": v[1]} for k, v in runs.items()},
    }
    OUT.write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps({"probe": probe, "runs": results, "environment": record["environment"]}, indent=1))


if __name__ == "__main__":
    main()
