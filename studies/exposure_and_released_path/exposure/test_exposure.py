"""Detector checks on hand-written inputs. Run: python3 -m pytest -q studies/exposure_and_released_path/exposure"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exposure as E  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
P = E.load_parser(ROOT)


def qf(q):
    return E.query_features(q, P)


def test_order_and_limit():
    f = qf("MATCH (n:A) RETURN n.name AS name ORDER BY name LIMIT 3")
    assert f["Q_ORDER_TRIGGER"] and f["Q_FINAL_ORDER_BY"] and f["Q_LIMIT"] and not f["Q_ORDER_BY_NO_LIMIT"]
    f = qf("MATCH (n:A) WITH n ORDER BY n.x DESC LIMIT 1 RETURN n.name AS name")
    assert f["Q_ORDER_TRIGGER"] and not f["Q_FINAL_ORDER_BY"] and not f["Q_LIMIT"]
    f = qf("MATCH (n:A {note: 'sort order by name'}) RETURN n.name AS name")
    assert f["Q_ORDER_TRIGGER"] and not f["Q_FINAL_ORDER_BY"]  # raw substring, as the scorers test it


def test_items():
    f = qf("MATCH (a:A)-[r:R]->(b) RETURN DISTINCT a, count(b), avg(b.v) AS m, collect(b.name) AS names")
    assert f["Q_RETURN_DISTINCT"] and f["Q_AGGREGATE"] and f["Q_FLOAT_EXPR"] and f["Q_MULTI_ITEM"]
    assert f["Q_UNALIASED_ITEM"] and f["Q_COLLECTION_EXPR"] and f["Q_GRAPH_VALUE_ITEM"]
    f = qf("MATCH (a:A) RETURN a.name AS name")
    assert not any(f[k] for k in ["Q_RETURN_DISTINCT", "Q_AGGREGATE", "Q_FLOAT_EXPR", "Q_MULTI_ITEM",
                                  "Q_UNALIASED_ITEM", "Q_COLLECTION_EXPR", "Q_GRAPH_VALUE_ITEM"])
    assert qf("MATCH (a)-[r]->(b) RETURN r")["Q_GRAPH_VALUE_ITEM"]
    assert qf("MATCH p = (a)-->(b) RETURN p")["Q_GRAPH_VALUE_ITEM"]
    assert qf("MATCH (a) RETURN a {.name} AS m")["Q_COLLECTION_EXPR"]
    assert qf("MATCH (a) RETURN toFloat(a.x) / 2 AS r")["Q_FLOAT_EXPR"]


def test_optional_union_unparsed():
    assert qf("MATCH (a) OPTIONAL MATCH (a)-->(b) RETURN b.x AS x")["Q_OPTIONAL_MATCH"]
    f = qf("MATCH (a:A) RETURN a.x AS x UNION MATCH (b:B) RETURN b.x AS x")
    assert f["Q_UNION"] and f["Q_UNPARSED"] and f["Q_MULTI_ITEM"] is None


def test_results():
    f, mm = E.result_features([{"a": "x", "b": 1}, {"a": "y", "b": None}, {"a": "x", "b": 1}])
    assert f["R_NUMERIC_NULL_COL"] and f["R_NULL"] and f["R_DUPLICATE_ROWS"] and f["R_MULTI_COL"] and not mm
    f, _ = E.result_features([{"a": None, "b": "s"}])
    assert f["R_NULL"] and not f["R_NUMERIC_NULL_COL"]  # all-NULL column is not the NaN trigger
    f, _ = E.result_features([{"a": "s"}, {"a": None}])
    assert not f["R_NUMERIC_NULL_COL"]
    f, _ = E.result_features([{"v": 3}, {"v": 3.0}, {"v": 2.5}])
    assert f["R_INT_FLOAT_MIXED_COL"] and f["R_NONINTEGRAL_FLOAT"] and f["R_FLOAT"]
    f, _ = E.result_features([{"v": 3.0}])
    assert f["R_FLOAT"] and not f["R_NONINTEGRAL_FLOAT"]
    f, _ = E.result_features([{"v": [1, 2], "m": {"k": 1}}])
    assert f["R_LIST"] and f["R_MAP"]
    f, _ = E.result_features([{"v": True}])
    assert not f["R_NUMERIC"]
    f, _ = E.result_features([])
    assert f["R_EMPTY"] and not f["R_MULTI_ROW"]
