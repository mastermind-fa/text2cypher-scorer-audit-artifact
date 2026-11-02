"""study S23 offline tests (no database, no scorer). Run: .venv/bin/python -m pytest -q tests/test_s23.py"""
import hashlib, inspect, json, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.join(HERE, "..", "code")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, CODE)
import s23_parse as P
import s23_rules as R
import s23_oracle as O
import s23_replication as REP

MTQ = os.path.join(ROOT, "external", "mind_the_query")


def res(keys, rows): return {"keys": keys, "rows": [dict(zip(keys, r)) for r in rows]}


def g(q, graph="er"): return {"graph": graph, "gold_cypher": q}


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


# ---- parser -------------------------------------------------------------------------------------------------------
def test_parser_single_line_and_tail():
    p = P.split_query("MATCH (u:User) RETURN DISTINCT u.name AS n, count(*) ORDER BY n DESC LIMIT 3")
    assert p["distinct"] and p["items"] == ["u.name AS n", "count(*)"] and p["order_by"] == "n DESC"
    assert p["skip_limit"] == ["LIMIT 3"] and P.rebuild(p) == "MATCH (u:User) RETURN DISTINCT u.name AS n, count(*) ORDER BY n DESC LIMIT 3"


def test_parser_ignores_keywords_in_strings_and_rejects_multi_return():
    p = P.split_query("MATCH (m:Movie {title: 'Return, Order by Limit'}) RETURN m.title")
    assert p and p["items"] == ["m.title"] and p["order_by"] is None
    assert P.split_query("MATCH (a) RETURN a UNION MATCH (b) RETURN b") is None
    assert P.split_query("MATCH (a) CALL { RETURN 1 AS x } RETURN a") is None


def test_column_names_and_backtick_alias():
    assert P.column_name("u.firstName") == "u.firstName" and P.column_name("count(m) AS c") == "c"
    assert P.as_item("toFloat(count(m))", "count(m)") == "toFloat(count(m)) AS `count(m)`"
    assert P.normalise_source("  MATCH (n) RETURN n.x;  ") == "MATCH (n) RETURN n.x"


# ---- rules --------------------------------------------------------------------------------------------------------
def test_build_is_deterministic_and_sources_used_once():
    a = R.build(MTQ)[3]; b = R.build(MTQ)[3]
    assert a == b and a
    used = {}
    for c in a: used.setdefault((c["graph"], c["source_gold_cypher"]), set()).add(c["class"])
    assert all(len(v) == 1 for v in used.values())
    assert all(c["reference_cypher"] != c["candidate_cypher"] for c in a)


def test_eligibility_rule():
    gold, raw = R.load_sources(MTQ)
    assert raw == 1829 and len(gold) == 1086
    assert {x["graph"] for x in gold} == set(R.GRAPHS)


def test_r1_uses_schema_integer_or_count():
    ints = {"er": {"Movie": {"year"}}}
    out = R.r1(g("MATCH (m:Movie) RETURN m.title, m.year"), ints)
    assert out == [("R1", "MATCH (m:Movie) RETURN m.title, toFloat(m.year) AS `m.year`")]
    assert R.r1(g("MATCH (m:Movie) RETURN m.title"), ints) == []
    assert "toFloat(count(m)) AS c" in R.r1(g("MATCH (m:Movie) RETURN count(m) AS c"), {})[0][1]


def test_r2_rules():
    out = R.r2(g("MATCH (m:Movie) RETURN m.genre AS g, AVG(m.year) AS a"))
    assert [r for r, _ in out] == ["R2A", "R2B"] and "toFloat(SUM(m.year)) / COUNT(m.year) AS a" in out[0][1]


def test_r3_r6_order_rules():
    assert R.r3(g("MATCH (m:Movie) RETURN m.title, m.year AS y"))[0][1].endswith("ORDER BY m.title DESC, y DESC")
    assert R.r3(g("MATCH (m:Movie) RETURN m.title ORDER BY m.title")) == []
    assert R.r6(g("MATCH (m:Movie) RETURN m.title AS t ORDER BY t")) == [("R6", "MATCH (m:Movie) RETURN m.title AS t")]
    assert R.r6(g("MATCH (m:Movie) RETURN m.title AS t ORDER BY t LIMIT 5")) == []
    assert R.r6(g("MATCH (m:Movie) WITH m ORDER BY m.y LIMIT 3 RETURN m.title AS t ORDER BY t")) == []


def test_r4_r5_r7_r8_c0_rules():
    assert R.r4(g("MATCH (m:Movie) RETURN DISTINCT m.title")) == [("R4", "MATCH (m:Movie) RETURN m.title")]
    assert R.r5(g("MATCH (m:Movie) RETURN m.title AS t, m.year")) == [("R5", "MATCH (m:Movie) RETURN m.year, m.title AS t")]
    assert R.r5(g("MATCH (m:Movie) RETURN m.title")) == []
    assert R.r7(g("MATCH (g:Genre)<-[:HAS]-(m) RETURN g.name AS n, collect(m.title) AS ts"))[0][1].endswith(
        "reverse(collect(m.title)) AS ts")
    assert "coalesce(m.title, null) AS `m.title`" in R.r8(g("MATCH (m:Movie) RETURN m.title"))[0][1]
    assert R.c0(g("MATCH (m:Movie) RETURN m.title AS t ORDER BY t"))[0][1].endswith("RETURN m.title AS t_value ORDER BY t_value")
    assert R.c0(g("MATCH (m:Movie) RETURN m.title")) == []


# ---- oracle class rules ---------------------------------------------------------------------------------------------
def test_r1_r2_r7_single_column_difference():
    ok, _ = O.check("R1_numeric_type", res(["a", "n"], [["x", 3]]), res(["a", "n"], [["x", 3.0]]))
    assert ok
    assert not O.check("R1_numeric_type", res(["a", "n"], [["x", 3]]), res(["a", "n"], [["y", 3.0]]))[0]
    assert not O.check("R2_float_tolerance", res(["a"], [[1.5]]), res(["a"], [[1.5]]))[0]
    assert O.check("R2_float_tolerance", res(["a"], [[1.5]]), res(["a"], [[1.5 + 1e-12]]))[0]
    assert not O.check("R2_float_tolerance", res(["a"], [[1.5]]), res(["a"], [[1.5 + 1e-6]]))[0]
    assert O.check("R7_list_order", res(["k", "l"], [["a", [1, 2]]]), res(["k", "l"], [["a", [2, 1]]]))[0]
    assert not O.check("R7_list_order", res(["k", "l"], [["a", [1]]]), res(["k", "l"], [["a", [1]]]))[0]
    assert not O.check("R7_list_order", res(["l"], [[[1, 2]]]), res(["l"], [[[2, 3]]]))[0]


def test_r3_r4_r6_row_rules():
    a, b = res(["x"], [[1], [2]]), res(["x"], [[2], [1]])
    assert O.check("R3_row_order", a, b, "MATCH (n) RETURN n.x AS x")[0]
    assert not O.check("R3_row_order", a, b, "MATCH (n) RETURN n.x AS x ORDER BY x")[0]
    assert O.check("R6_reference_order", a, b, "MATCH (n) RETURN n.x AS x ORDER BY x", "MATCH (n) RETURN n.x AS x")[0]
    assert not O.check("R6_reference_order", a, a, "MATCH (n) RETURN n.x AS x ORDER BY x", "MATCH (n) RETURN n.x AS x")[0]
    assert O.check("R4_duplicates", res(["x"], [[1], [2]]), res(["x"], [[1], [1], [2]]))[0]
    assert not O.check("R4_duplicates", res(["x"], [[1], [2]]), res(["x"], [[2], [1], [1]]))[0]


def test_r5_column_order_rule():
    ref = res(["a", "b"], [["x", 1], ["y", 2]])
    assert O.check("R5_column_order", ref, res(["b", "a"], [[1, "x"], [2, "y"]]))[0]
    assert not O.check("R5_column_order", ref, res(["b", "a"], [[2, "y"], [1, "x"]]))[0]   # row order changed too
    assert not O.check("R5_column_order", ref, res(["b", "a"], [[1.0, "x"], [2, "y"]]))[0]  # type changed


def test_r8_natural_null_and_profile():
    ok, det = O.check("R8_null_natural", res(["a", "s"], [[1, None], [None, "t"]]), res(["a", "s"], [[1, None], [None, "t"]]))
    assert ok and det["null_columns"]["a"]["type"] == "numeric" and det["null_columns"]["s"]["type"] == "text"
    assert not O.check("R8_null_natural", res(["a"], [[1]]), res(["a"], [[1]]))[0]
    assert not O.check("R8_null_natural", res(["a"], [[None]]), res(["a"], [[None]]))[0]


def test_common_exclusions():
    assert not O.check("R3_row_order", res(["x"], []), res(["x"], []))[0]
    c = {"reference_cypher": "SELECT a FROM t", "candidate_cypher": "MATCH (n) RETURN n", "class": "R3_row_order"}
    assert O.evaluate(c, lambda q: res(["x"], [[1]]))[1] == "SQL-looking text"
    c = {"reference_cypher": "MATCH (n) RETURN n.x", "candidate_cypher": "MATCH (n) RETURN n.x", "class": "R3_row_order"}
    assert O.evaluate(c, lambda q: res(["x"], [[1]]))[1] == "identical query text"
    seq = iter([res(["x"], [[1], [2]]), res(["x"], [[2], [1]]), res(["x"], [[1]]), res(["x"], [[1]])])
    c = {"reference_cypher": "MATCH (n) RETURN n.x AS x", "candidate_cypher": "MATCH (n) RETURN n.x AS x ORDER BY x",
         "class": "R3_row_order"}
    assert O.evaluate(c, lambda q: next(seq))[1] == "non-deterministic result"

    def boom(q): raise O.NonJSON("non-JSON value Date")
    c["reference_cypher"] = "MATCH (n) RETURN n.d AS x"
    assert O.evaluate(c, boom)[1].startswith("graph/temporal value")


def test_read_only_and_graph_guard_in_code():
    src = inspect.getsource(O.run_read) + inspect.getsource(O.eval_graph)
    assert "execute_read" in src and "graph changed during read-only oracle" in src
    assert "DETACH DELETE" not in inspect.getsource(O)


def test_select_first_passing_variant_and_quota():
    rs = [{"class": "R2_float_tolerance", "rank": r, "sub_rank": s, "oracle_pass": p, "oracle_reason": "x"}
          for r, s, p in [(1, 0, False), (1, 1, True), (2, 0, True), (2, 1, True)]]
    adm, rej = O.select(rs)
    assert [(a["rank"], a["sub_rank"]) for a in adm] == [(1, 1), (2, 0)] and len(rej) == 2


# ---- replication rubric -------------------------------------------------------------------------------------------
S20_D1 = {"cypherturn": "REJECT", "cypherbench": "ACCEPT", "gqlbench": "ACCEPT", "tugraph": "ACCEPT",
          "pipecypher": "REJECT", "cypherlens": "REJECT", "cyspider": "ACCEPT"}


def test_category_and_classify():
    assert REP.category(["1", "1"]) == "ACCEPT" and REP.category(["0", "1"]) == "MIXED"
    assert REP.category(["ERROR:TypeError"]) == "ERROR" and REP.category([]) == "NONE"
    assert REP.classify(S20_D1, dict(S20_D1), 10)[0] == "EXACT_REPLICATION"
    one = dict(S20_D1, cypherlens="ACCEPT")
    assert REP.classify(S20_D1, one, 10)[0] == "PARTIAL_REPLICATION"
    three = dict(S20_D1, cypherlens="ACCEPT", pipecypher="ACCEPT", cypherturn="ACCEPT")
    assert REP.classify(S20_D1, three, 10)[0] == "NO_REPLICATION"   # also: split vanished
    assert REP.classify(S20_D1, dict(S20_D1), 4)[0] == "NOT_TESTABLE"


def test_r8_mechanism_rule():
    cases = [{"case_id": f"c{i}", "null_columns": {"a": {"type": "numeric" if i == 0 else "text"}}} for i in range(5)]
    v = {c["case_id"]: {s: "1" for s in REP.PRIMARY} for c in cases}
    v["c0"]["gqlbench"] = "0"
    assert REP.classify_r8(cases, v)[0] == "EXACT_REPLICATION"
    v["c1"]["gqlbench"] = "0"
    assert REP.classify_r8(cases, v)[:2] == ("PARTIAL_REPLICATION", ["gqlbench"])


def test_study_decision_rule():
    st = {c: "EXACT_REPLICATION" for c in REP.SHARED_EVIDENCE} | {"R5_column_order": "NEW_EVIDENCE"}
    assert REP.session_decision(st)[0].startswith("A_")
    st2 = dict(st, R1_numeric_type="NO_REPLICATION")
    assert REP.session_decision(st2)[0].startswith("B_")
    st3 = {c: "NO_REPLICATION" for c in REP.SHARED_EVIDENCE}
    assert REP.session_decision(st3)[0].startswith("C_")
    st4 = {c: "NOT_TESTABLE" for c in REP.SHARED_EVIDENCE}
    assert REP.session_decision(st4)[0].startswith("D_")


def test_reference_patterns_from_frozen_s20():
    p = REP.patterns_from_csv(os.path.join(ROOT, "studies/native_cypherturn_stress/native_equivalence_stress/frozen/"
                                                 "20261030T143804Z_results/s20_verdicts.csv"), "class")
    assert p["D1_numeric_type"] == S20_D1
    assert p["D3_row_order"]["tugraph"] == "REJECT" and p["D5_null_controlled"]["gqlbench"] == "MIXED"


# ---- integrity ----------------------------------------------------------------------------------------------------
def test_adapter_and_runner_integrity():
    assert sha(os.path.join(ROOT, "studies/adapter_readiness/audit_readiness/code/audit_adapters.py")).startswith("bcc4db64")
    am = open(os.path.join(ROOT, "studies/corpus_audit/audit_analysis/ANALYSIS_FREEZE_AMENDMENT_1.json")).read()
    runner = sha(os.path.join(ROOT, "studies/corpus_audit/audit_analysis/code/run_experiment_v1_1.py"))
    assert runner == "6ad22b285c46a16c2a0216403d3b2ebc1a9463f471278327ca626022d2bb0e74" and runner in am


def test_frozen_constants():
    assert R.EPSILON_REL == 1e-9 and R.SEED == 23 and R.RESERVE == 80 and REP.MIN_N == 5
    assert sum(R.QUOTA.values()) == 85


def test_mtq_pin():
    import subprocess
    head = subprocess.run(["git", "-C", MTQ, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert head == "ec4054a1b7df7e6310efa95c56bb6e7cebc4d161"
    assert not os.path.exists(os.path.join(MTQ, ".env"))
