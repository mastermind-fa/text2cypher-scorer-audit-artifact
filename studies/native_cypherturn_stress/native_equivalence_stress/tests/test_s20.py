"""study S20 offline tests (no database, no scorer). Run: .venv/bin/python -m pytest -q tests/test_s20.py"""
import hashlib, inspect, json, os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.join(HERE, "..", "code")
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, CODE)
import s20_rules as R
import s20_oracle as O

CT = os.path.join(ROOT, "external", "cypherturn")
S18 = os.path.join(ROOT, "studies", "native_cypherturn_validation", "native_cypher", "frozen", "20261030T083217Z_native_cypher_input", "cases.jsonl")


def res(keys, rows): return {"keys": keys, "rows": [dict(zip(keys, r)) for r in rows]}


def g(q, ans=None, graph="ancient_empire"):
    return {"graph": graph, "session_id": "s", "turn_id": 1, "gold_cypher": q, "gold_answer": ans}


# ---- deterministic transformations -------------------------------------------------------------
def test_build_is_deterministic():
    a = R.build(CT, S18)[2]; b = R.build(CT, S18)[2]
    assert a == b and len(a) > 0


def test_d1_rule():
    out = R.d1(g("MATCH (n:City)\nRETURN count(n) AS c", [{"c": 3}]))
    assert out == [("D1", "MATCH (n:City)\nRETURN toFloat(count(n)) AS c")]
    assert R.d1(g("MATCH (n:City)\nRETURN avg(n.x) AS c", [{"c": 3.5}])) == []
    assert R.d1(g("MATCH (n:City)\nRETURN n.flag AS c", [{"c": True}])) == []


def test_d2_rules_and_balanced():
    out = R.d2(g("MATCH (n:City)\nRETURN AVG(n.population) AS a"))
    assert [r for r, _ in out] == ["D2A", "D2B"]
    assert "toFloat(SUM(n.population)) / COUNT(n.population) AS a" in out[0][1]
    assert "AVG(n.population) / 3.0 * 3.0 AS a" in out[1][1]
    assert R.d2(g("MATCH (n:City)\nRETURN AVG(n.a) + AVG(n.b) AS a")) == []


def test_d3_rule_requires_unordered_reference():
    q = "MATCH (n:City)\nRETURN DISTINCT n.name AS name"
    assert R.d3(g(q, [{"name": "a"}, {"name": "b"}]))[0][1].endswith("ORDER BY name DESC")
    assert R.d3(g(q + "\nLIMIT 3", [{"name": "a"}, {"name": "b"}])) == []
    assert R.d3(g("MATCH (n:City)\nWITH n ORDER BY n.x\nRETURN n.name AS name", [{"name": "a"}, {"name": "b"}])) == []
    assert R.d3(g(q, [{"name": "a"}])) == []


def test_d4_rule_drops_distinct_only():
    out = R.d4(g("MATCH (n:City)\nRETURN DISTINCT n.name AS name"))
    assert out == [("D4", "MATCH (n:City)\nRETURN n.name AS name")]
    assert R.d4(g("MATCH (n:City)\nRETURN n.name AS name")) == []


def test_d5_rule_skips_mentioned_properties():
    het = {"ancient_empire": {"Citizen": ["occupation", "zz"]}}
    q = "MATCH (m:Citizen)\nWHERE m.occupation IS NOT NULL\nRETURN m.name AS name"
    (_, ref, cand), = R.d5(g(q), het)
    assert "m.zz AS p_opt" in ref and "coalesce(m.zz, null) AS p_opt" in cand


# ---- exact equivalence-class labelling / oracle rules ------------------------------------------
def test_type_detection_d1():
    ok, d = O.check("D1_numeric_type", res(["c"], [[3], [5]]), res(["c"], [[3.0], [5.0]]))
    assert ok and d["type_ref"] == "int"
    assert not O.check("D1_numeric_type", res(["c"], [[3]]), res(["c"], [[3]]))[0]       # no type change
    assert not O.check("D1_numeric_type", res(["c"], [[3]]), res(["c"], [[3.5]]))[0]     # value change
    assert not O.check("D1_numeric_type", res(["c"], [[True]]), res(["c"], [[1.0]]))[0]  # bool is not int


def test_float_delta_d2():
    a = 58.0; b = 57.99999999999999
    ok, d = O.check("D2_float_tolerance", res(["x"], [[a]]), res(["x"], [[b]]))
    assert ok and d["max_abs_delta"] == abs(b - a) > 0
    assert O.check("D2_float_tolerance", res(["x"], [[a]]), res(["x"], [[a]])) == (False, "zero delta (exactly equal; not a tolerance case)")
    assert not O.check("D2_float_tolerance", res(["x"], [[a]]), res(["x"], [[58.001]]))[0]
    assert not O.check("D2_float_tolerance", res(["x"], [[58]]), res(["x"], [[57.99999999999999]]))[0]  # type change


def test_order_equality_inequality_d3():
    ref = res(["n"], [["a"], ["b"], ["c"]])
    assert O.check("D3_row_order", ref, res(["n"], [["c"], ["b"], ["a"]]), "MATCH (x) RETURN x.n AS n")[0]
    assert not O.check("D3_row_order", ref, ref, "MATCH (x) RETURN x.n AS n")[0]
    assert not O.check("D3_row_order", ref, res(["n"], [["c"], ["b"]]), "MATCH (x) RETURN x.n AS n")[0]
    assert not O.check("D3_row_order", ref, res(["n"], [["c"], ["b"], ["a"]]), "MATCH (x) RETURN x.n AS n LIMIT 3")[0]


def test_multiset_and_set_d4():
    ref = res(["n"], [["a"], ["b"]])
    ok, d = O.check("D4_duplicates", ref, res(["n"], [["a"], ["a"], ["b"]]))
    assert ok and d["duplicate_rows"] == 1
    assert not O.check("D4_duplicates", ref, res(["n"], [["a"], ["b"]]))[0]               # multiset equal
    assert not O.check("D4_duplicates", ref, res(["n"], [["b"], ["a"], ["a"]]))[0]        # order differs too
    assert not O.check("D4_duplicates", ref, res(["n"], [["a"], ["c"], ["c"]]))[0]        # set differs


def test_null_positions_d5():
    ref = res(["name", "p_opt"], [["a", None], ["b", 3]])
    assert O.check("D5_null_controlled", ref, res(["name", "p_opt"], [["a", None], ["b", 3]]))[0]
    assert not O.check("D5_null_controlled", ref, res(["name", "p_opt"], [["a", 3], ["b", None]]))[0]
    assert not O.check("D5_null_controlled", res(["name", "p_opt"], [["a", 1]]), res(["name", "p_opt"], [["a", 1]]))[0]


def test_column_control_d6():
    assert O.check("D6_column_name_control", res(["a"], [[1]]), res(["a_value"], [[1]]))[0]


def test_empty_reference_rejected():
    assert O.check("D3_row_order", res(["n"], []), res(["n"], []), "") == (False, "empty reference result (vacuous)")


# ---- repeated execution, read-only, graph unchanged ------------------------------------------------
def test_repeated_execution_detects_nondeterminism():
    calls = {"n": 0}
    def run(q):
        calls["n"] += 1
        return res(["n"], [["a"], ["b"]] if calls["n"] % 2 else [["b"], ["a"]])
    c = {"class": "D3_row_order", "reference_cypher": "MATCH (x) RETURN x.n AS n", "candidate_cypher": "MATCH (x) RETURN x.n AS n\nORDER BY n DESC"}
    ok, why, _, _ = O.evaluate(c, run)
    assert not ok and why == "non-deterministic result" and calls["n"] == 4


def test_read_only_and_graph_guard_in_code():
    assert "execute_read" in inspect.getsource(O.run_read)
    src = inspect.getsource(O.main)
    assert "before != after" in src and "graph changed during read-only oracle" in src


# ---- traceability, Cypher-only, selection --------------------------------------------------------
def test_source_traceability_and_cypher_only():
    gold, _, cands = R.build(CT, S18)
    keys = {(x["graph"], x["gold_cypher"]) for x in gold}
    s18 = {(json.loads(l)["meta"]["graph"], json.loads(l)["reference"]["query"]) for l in open(S18)}
    for c in cands:
        assert (c["graph"], c["source_gold_cypher"]) in keys
        assert (c["graph"], c["source_gold_cypher"]) not in s18
        assert c["reference_cypher"] != c["candidate_cypher"]
        assert not O.looks_sql(c["reference_cypher"]) and not O.looks_sql(c["candidate_cypher"])
        assert "RETURN" in c["candidate_cypher"]
        if c["class"] != "D5_null_controlled": assert c["reference_cypher"] == c["source_gold_cypher"]


def test_source_used_once_across_classes():
    cands = R.build(CT, S18)[2]
    owner = {}
    for c in cands:
        k = (c["graph"], c["source_gold_cypher"])
        assert owner.setdefault(k, c["class"]) == c["class"]


def test_select_first_passing_variant_and_quota():
    rs = []
    for rank in range(1, 30):
        rs.append({"class": "D2_float_tolerance", "rank": rank, "sub_rank": 0, "oracle_pass": rank % 2 == 0, "oracle_reason": "x"})
        rs.append({"class": "D2_float_tolerance", "rank": rank, "sub_rank": 1, "oracle_pass": True, "oracle_reason": "x"})
    adm, rej = O.select(rs)
    assert len(adm) == R.QUOTA["D2_float_tolerance"]
    assert [a["sub_rank"] for a in adm[:2]] == [1, 0]
    assert len({a["rank"] for a in adm}) == len(adm)


# ---- adapter integrity, freeze integrity ---------------------------------------------------------
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def test_adapter_and_runner_integrity():
    assert sha(os.path.join(ROOT, "studies/adapter_readiness/audit_readiness/code/audit_adapters.py")).startswith("bcc4db64")
    am = open(os.path.join(ROOT, "studies/corpus_audit/audit_analysis/ANALYSIS_FREEZE_AMENDMENT_1.json")).read()
    runner = sha(os.path.join(ROOT, "studies/corpus_audit/audit_analysis/code/run_experiment_v1_1.py"))
    assert runner == "6ad22b285c46a16c2a0216403d3b2ebc1a9463f471278327ca626022d2bb0e74" and runner in am


def test_freeze_integrity_verification():
    sys.path.insert(0, CODE)
    import s20_score as S
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "cases.jsonl"), "w").write("{}\n")
        open(os.path.join(d, "hashes.sha256"), "w").write(f"{sha(os.path.join(d, 'cases.jsonl'))}  cases.jsonl\n")
        S.verify_freeze(d)
        open(os.path.join(d, "cases.jsonl"), "a").write("tamper\n")
        try:
            S.verify_freeze(d); assert False
        except AssertionError as e:
            assert "freeze violated" in str(e)


def test_epsilon_frozen_value():
    assert R.EPSILON_REL == 1e-9 and R.SEED == 20 and R.RESERVE == 40
