"""MAIN_AUDIT thin adapters (audit-adapters-v1).

Contract (protocol audit-protocol-v1 §P3, the adapter-readiness check §7–8):
  MAIN_AUDIT pair  = {"case_id", "reference": {"query", "columns", "rows"}, "prediction": {"query", "columns", "rows"}}
             rows are lists aligned with columns; values are JSON-level Python values.
  adapter  = representation change ONLY: rows -> the native structure the scorer's own pipeline would hand to its
             comparator (list of dicts / pandas DataFrame via the driver's to_df / py2neo-style .data()), then a call to
             the UNMODIFIED scorer function, then extraction of its native verdict.
  Never: sorting, renaming, deduplication, type coercion, NULL conversion, tolerance, alias changes, bug fixes.

Each adapter returns (native_output_repr: str, verdict: int in {0,1}). The verdict is the scorer's own pass/fail:
  CypherTurn float 1.0/0.0 | CypherBench float | GQLBench first element of (score, msg) | TuGraph compute() accuracy
  over one pair | PIPE-Cypher AnswerSetScores.exact | CypherLens exact_match 1/0 | CySpider True/False |
  neo4j-labs df_sim_pair score == 1.0 (secondary, protocol-declared threshold) | pc-v1.1 primary()[0].

Adapters are loaded one scorer per process (run_adapter.py) so that top-level module names in different repos
(`models`, `services`, `impl`, `driver`, `Config`) cannot collide.
"""
import ast
import copy
import io
import json
import os
import random
import sys
import types
import contextlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
EXT = os.path.join(ROOT, "external")

PRIMARY = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider"]
SECONDARY = ["neo4jlabs", "pc_v1_1"]
SEED = 42  # protocol P3: random.seed(42) immediately before each CypherBench / GQLBench call


class AdapterInputConflict(Exception):
    """Reference and prediction share identical query text but different rows: a replay connector keyed by query
    text cannot represent that faithfully, so the case is refused instead of guessed."""


def as_dicts(side):
    """Row lists -> list of dicts in column order (what neo4j `dict(record)` / `.data()` returns). Deep-copied so a
    scorer that mutates its inputs cannot affect another call."""
    return [dict(zip(side["columns"], copy.deepcopy(r))) for r in side["rows"]]


def replay_map(pair):
    rq, pq = pair["reference"]["query"], pair["prediction"]["query"]
    if rq == pq and (pair["reference"]["rows"] != pair["prediction"]["rows"]
                     or pair["reference"]["columns"] != pair["prediction"]["columns"]):
        raise AdapterInputConflict(pair["case_id"])
    return {rq: pair["reference"], pq: pair["prediction"]}


class ReplayConnector:
    """Stands in for the scorer's Neo4j connector: run_query returns the frozen rows of that query as list of dicts
    (the native `[dict(record) for record in result]`)."""

    def __init__(self, pair):
        self._m = replay_map(pair)
        self.calls = []

    def run_query(self, cypher, timeout=120, **params):
        self.calls.append(cypher)
        return as_dicts(self._m[cypher])


def _path(*p):
    d = os.path.join(EXT, *p)
    if d not in sys.path:
        sys.path.insert(0, d)


# --------------------------------------------------------------------------------------------------- CypherTurn
def load_cypherturn():
    _path("cypherturn")
    from graph_eval_utils.metrics.execution_accuracy import execution_accuracy

    def score(pair):
        out = execution_accuracy(pair["prediction"]["query"], pair["reference"]["query"], ReplayConnector(pair))
        return repr(out), int(out == 1.0)
    return score


# -------------------------------------------------------------------------------------------------- CypherBench
def load_cypherbench():
    _path("cypherbench")
    from cypherbench.metrics.execution_accuracy import execution_accuracy

    def score(pair):
        random.seed(SEED)
        out = execution_accuracy(pair["prediction"]["query"], pair["reference"]["query"], ReplayConnector(pair))
        return repr(out), int(out == 1.0)
    return score


# ----------------------------------------------------------------------------------------------------- GQLBench
def _stub_nebula():
    """nebulagraph_python is imported at module level but used only by the NebulaGraph path (gql_dialect != 'cypher').
    Empty placeholder modules/classes; never called on the Cypher path."""
    names = {"nebulagraph_python": ["NebulaClient", "SessionConfig", "SessionPoolConfig"],
             "nebulagraph_python.client": [], "nebulagraph_python.client._connection": ["ConnectionConfig"],
             "nebulagraph_python.data": ["HostAddress"]}
    for mod, attrs in names.items():
        m = types.ModuleType(mod)
        for a in attrs:
            setattr(m, a, type(a, (), {}))
        sys.modules.setdefault(mod, m)


class _FakeNeo4jDriver:
    """Replaces neo4j.GraphDatabase for GQLBench's own cypher_execute(). execute_query emulates the transformer
    GQLBench passes (neo4j.Result.to_df with defaults expand=False, parse_dates=False), whose source in the
    installed driver 5.26.0 is exactly `pd.DataFrame(self.values(), columns=self._keys)`. Everything after that
    (the nested cypher_value_to_python_value, itertuples, res_eq) is GQLBench's unmodified code."""

    def __init__(self, pair):
        self._m = replay_map(pair)

    def driver(self, uri, auth=None):
        return self

    def execute_query(self, query, database_=None, result_transformer_=None, **kw):
        import pandas as pd
        text = getattr(query, "text", query)
        side = self._m[text]
        return pd.DataFrame(copy.deepcopy(side["rows"]), columns=side["columns"])

    def close(self):
        pass


def load_gqlbench():
    _stub_nebula()
    _path("gqlbench", "Code")
    _path("gqlbench", "Code", "eval")
    import execute_accuracy as ea
    ea.time.sleep = lambda s: None  # 0.1 s pacing sleep between live DB calls; no semantic role

    def score(pair):
        ea.GraphDatabase = _FakeNeo4jDriver(pair)
        random.seed(SEED)
        with contextlib.redirect_stdout(io.StringIO()):
            out = ea.execution_accuracy(pair["prediction"]["query"], pair["reference"]["query"], "audit", "cypher", "audit")
        return repr(out), int(bool(out[0]))
    return score


# ------------------------------------------------------------------------------------------ TuGraph / Text2GQL
def load_tugraph():
    sys.modules.setdefault("evaluate", types.ModuleType("evaluate"))  # used only by GoogleBleu (not called)
    _path("tugraph_driver")
    from impl.evaluation.metrics import ExecutionAccuracy

    class ReplayDriver:
        """Native TuGraph driver.query returns session.run(cypher).data() -> list of dicts."""

        def __init__(self, pair):
            self._m = replay_map(pair)

        def query(self, cypher, db_name="default"):
            return as_dicts(self._m[cypher])

    def score(pair):
        out = ExecutionAccuracy(ReplayDriver(pair)).compute([pair["prediction"]["query"]],
                                                            [pair["reference"]["query"]], db_id="audit")
        return repr(out), int(out == 1.0)
    return score


# ------------------------------------------------------------------------------------------------- PIPE-Cypher
def load_pipecypher():
    _path("pipecypher")
    from pipecypher.evaluation import answer_set_scores

    def score(pair):
        out = answer_set_scores(as_dicts(pair["prediction"]), as_dicts(pair["reference"]))
        return repr(out), int(bool(out.exact))
    return score


# -------------------------------------------------------------------------------------------------- CypherLens
def load_cypherlens():
    _path("cypherlens")
    from services.result_comparator import ResultComparator
    from services.column_similarity import ColumnSimilarityMatcher
    from services.metrics_calculator import MetricsCalculator
    from models.CSVRow import CSVRow
    from models.EvaluationRow import EvaluationRow
    import logging
    logging.getLogger("services").setLevel(logging.WARNING)
    comparator = ResultComparator(ColumnSimilarityMatcher(threshold=0.60))  # main.py default wiring
    metrics = MetricsCalculator()

    def score(pair):
        row = EvaluationRow(CSVRow(question="", schema="", cypher=pair["reference"]["query"], database_name="audit"),
                            gen_cypher=pair["prediction"]["query"], gen_results=as_dicts(pair["prediction"]),
                            org_results=as_dicts(pair["reference"]))
        comparator.build_table(row)
        out = metrics.compute_exact_match(row)
        return repr(out), int(out == 1)
    return score


# ---------------------------------------------------------------------------------------------------- CySpider
CYSPIDER_FILE = os.path.join(EXT, "cyspider", "semantic_parser", "metrics", "text2cypher", "evaluator.py")


def extract_function_source(path, name):
    """Verbatim source of one top-level function (ast.get_source_segment). Used because the module performs a
    hard-coded config read and opens a Neo4j connection at import time."""
    src = open(path, encoding="utf-8").read()
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise LookupError(name)


def load_cyspider():
    fsrc = extract_function_source(CYSPIDER_FILE, "eval_exec_match")

    class Node:  # py2neo.data.Node placeholder: JSON values are never py2neo objects
        pass

    class Relationship:
        pass

    ns = {"Node": Node, "Relationship": Relationship}
    exec(compile(fsrc, CYSPIDER_FILE + "::eval_exec_match", "exec"), ns)
    fn = ns["eval_exec_match"]

    class _Cursor:
        def __init__(self, rows):
            self._rows = rows

        def data(self):  # py2neo Cursor.data() -> list of dicts
            return self._rows

    class ReplayGraph:
        def __init__(self, pair):
            self._m = replay_map(pair)

        def run(self, q):
            return _Cursor(as_dicts(self._m[q]))

    def score(pair):
        with contextlib.redirect_stdout(io.StringIO()):
            out = fn(ReplayGraph(pair), pair["prediction"]["query"], pair["reference"]["query"])
        return repr(out), int(out is True)
    return score


# ------------------------------------------------------------------------------- neo4j-labs Jaccard (secondary)
NEO4JLABS_NB = os.path.join(EXT, "neo4jlabs_text2cypher", "evaluations", "evaluating_cypher_jaccard.ipynb")


def neo4jlabs_cell_source():
    nb = json.load(open(NEO4JLABS_NB, encoding="utf-8"))
    return "".join(nb["cells"][5]["source"])


def load_neo4jlabs():
    ns = {}
    exec("from typing import Set, Any, Union, Dict, List, Tuple, Hashable", ns)  # notebook cell 3 typing imports
    exec(compile(neo4jlabs_cell_source(), NEO4JLABS_NB + "::cell5", "exec"), ns)
    fn = ns["df_sim_pair"]

    def score(pair):
        out = fn((pair["reference"]["query"], as_dicts(pair["reference"])),
                 (pair["prediction"]["query"], as_dicts(pair["prediction"])))
        return repr(out), int(out == 1.0)
    return score


# ---------------------------------------------------------------------------------- project pc-v1.1 (reference)
def load_pc_v1_1():
    p = os.path.join(ROOT, "studies", "reference_comparator", "code")
    if p not in sys.path:
        sys.path.insert(0, p)
    import comparator_pc_v1_1 as pc

    def score(pair):
        out = pc.primary(as_dicts(pair["reference"]), as_dicts(pair["prediction"]))
        return repr(out), int(bool(out[0]))
    return score


LOADERS = {"cypherturn": load_cypherturn, "cypherbench": load_cypherbench, "gqlbench": load_gqlbench,
           "tugraph": load_tugraph, "pipecypher": load_pipecypher, "cypherlens": load_cypherlens,
           "cyspider": load_cyspider, "neo4jlabs": load_neo4jlabs, "pc_v1_1": load_pc_v1_1}

# Repository (EXTERNAL_PINS local_dir) behind each adapter; pc_v1_1 is project code.
PIN_DIR = {"cypherturn": "cypherturn", "cypherbench": "cypherbench", "gqlbench": "gqlbench",
           "tugraph": "tugraph_driver", "pipecypher": "pipecypher", "cypherlens": "cypherlens",
           "cyspider": "cyspider", "neo4jlabs": "neo4jlabs_text2cypher", "pc_v1_1": None}
