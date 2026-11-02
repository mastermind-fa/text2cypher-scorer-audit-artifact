"""the adapter-readiness check MAIN_AUDIT readiness tests. Smoke fixture only — S1/S2/S3 are never opened here."""
import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.join(HERE, "..", "code")
sys.path.insert(0, CODE)
import audit_adapters as A  # noqa: E402
import audit_readiness as R  # noqa: E402

PY = sys.executable
SMOKE = R.SMOKE


def run_adapter(name, fixture=SMOKE, repeats=2, hashseed=0):
    env = dict(os.environ, PYTHONHASHSEED=str(hashseed), PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([PY, os.path.join(CODE, "run_adapter.py"), name, fixture, "--repeats", str(repeats)],
                       capture_output=True, text=True, env=env, timeout=300)
    return p, (json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else None)


class TestPins(unittest.TestCase):
    def test_exact_repo_pins(self):
        pins = json.load(open(R.PINS))
        res = R.verify_pins()
        self.assertEqual(len(pins["repos"]), 8)
        for r in pins["repos"]:
            v = res[r["local_dir"]]
            self.assertTrue(v["ok"], r["local_dir"])
            self.assertEqual(v["local_commit"], r["commit"])
            self.assertEqual(len(r["commit"]), 40)
            self.assertFalse(v["dirty"])

    def test_every_adapter_maps_to_a_pin(self):
        local = {r["local_dir"] for r in json.load(open(R.PINS))["repos"]}
        for name, d in A.PIN_DIR.items():
            if d is not None:
                self.assertIn(d, local, name)


class TestAdapterContract(unittest.TestCase):
    side = {"query": "q", "columns": ["b", "a", "c"], "rows": [[2, None, "x"], [1, 1.0, " X"], [2, None, "x"]]}

    def test_input_conversion_preserves_order_values_duplicates(self):
        out = A.as_dicts(self.side)
        self.assertEqual([list(d.keys()) for d in out], [["b", "a", "c"]] * 3)  # column order kept
        self.assertEqual([list(d.values()) for d in out], self.side["rows"])     # row order + duplicates kept
        self.assertIsNone(out[0]["a"])                                          # NULL kept
        self.assertIsInstance(out[1]["a"], float)                               # no type coercion
        self.assertEqual(out[1]["c"], " X")                                     # no strip / case change

    def test_input_conversion_is_a_deep_copy(self):
        side = {"query": "q", "columns": ["l"], "rows": [[[3, 1, 2]]]}
        out = A.as_dicts(side)
        out[0]["l"].sort()
        self.assertEqual(side["rows"][0][0], [3, 1, 2])

    def test_no_semantic_normalization_in_adapter_code(self):
        tree = ast.parse(open(os.path.join(CODE, "audit_adapters.py")).read())
        banned = {"sorted", "set", "round", "frozenset"}
        banned_attr = {"lower", "upper", "strip", "sort", "drop_duplicates", "fillna", "astype", "rename"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, banned, ast.unparse(node))
                if isinstance(node.func, ast.Attribute):
                    self.assertNotIn(node.func.attr, banned_attr, ast.unparse(node))

    def test_conflicting_identical_query_text_is_refused(self):
        pair = {"case_id": "T", "reference": {"query": "Q", "columns": ["a"], "rows": [[1]]},
                "prediction": {"query": "Q", "columns": ["a"], "rows": [[2]]}}
        with self.assertRaises(A.AdapterInputConflict):
            A.replay_map(pair)

    def test_cyspider_extraction_is_verbatim(self):
        src = A.extract_function_source(A.CYSPIDER_FILE, "eval_exec_match")
        self.assertIn(src, open(A.CYSPIDER_FILE).read())
        self.assertTrue(src.startswith("def eval_exec_match(graph, p_str, g_str):"))

    def test_neo4jlabs_cell_is_verbatim(self):
        src = A.neo4jlabs_cell_source()
        self.assertIn("def df_sim_pair", src)
        nb = json.load(open(A.NEO4JLABS_NB))
        self.assertEqual(src, "".join(nb["cells"][5]["source"]))


class TestSmokeExecution(unittest.TestCase):
    def test_all_scorers_identity_and_changed_cell(self):
        """Verdict extraction: SMOKE-01 (identical) -> 1 and SMOKE-02 (changed cell) -> 0 for every scorer."""
        for name in A.PRIMARY + A.SECONDARY:
            with self.subTest(scorer=name):
                p, rec = run_adapter(name, repeats=1)
                self.assertTrue(rec and rec["import_ok"], p.stderr[-500:])
                v = {c["case_id"]: c["runs"][0]["verdict"] for c in rec["cases"]}
                self.assertEqual(v["SMOKE-01"], 1)
                self.assertEqual(v["SMOKE-02"], 0)
                self.assertFalse(rec["torch_or_cuda_loaded"])

    def test_deterministic_across_repeats_and_hashseeds(self):
        for name in ["pipecypher", "cyspider", "cypherbench"]:
            with self.subTest(scorer=name):
                _, a = run_adapter(name, repeats=3, hashseed=0)
                _, b = run_adapter(name, repeats=3, hashseed=7)
                sig = lambda r: [[(x["native"], x["verdict"]) for x in c["runs"]] for c in r["cases"]]
                self.assertEqual(sig(a), sig(b))
                for runs in sig(a):
                    self.assertEqual(len(set(runs)), 1)


class TestFailureHandlingAndGate(unittest.TestCase):
    def test_unknown_scorer_reports_import_failure(self):
        _, rec = run_adapter("no_such_scorer", repeats=1)
        self.assertFalse(rec["import_ok"])
        cls, _, _ = R.classify("pipecypher", True, [rec, rec], json.load(open(R.EXPECTED)))
        self.assertEqual(cls, "MISSING_RUNTIME_COMPONENT")

    def test_pin_failure_excludes_scorer(self):
        cls, _, notes = R.classify("cypherturn", False, [{}, {}], json.load(open(R.EXPECTED)))
        self.assertEqual(cls, "NOT_RUNNABLE")

    def test_network_error_excludes_scorer(self):
        rec = {"import_ok": True, "torch_or_cuda_loaded": False,
               "cases": [{"case_id": "SMOKE-01", "runs": [{"error": "NetworkBlocked: x"}]}]}
        cls, _, _ = R.classify("tugraph", True, [rec, rec], json.load(open(R.EXPECTED)))
        self.assertEqual(cls, "NOT_RUNNABLE")

    def test_gate_pass_at_four(self):
        classes = {s: "NOT_RUNNABLE" for s in A.PRIMARY}
        for s in A.PRIMARY[:4]:
            classes[s] = "RUNNABLE_WITH_THIN_ADAPTER"
        self.assertEqual(R.import_gate(classes), ("PASS", 4))

    def test_gate_fail_below_four(self):
        classes = {s: "NOT_RUNNABLE" for s in A.PRIMARY}
        for s in A.PRIMARY[:3]:
            classes[s] = "RUNNABLE_UNCHANGED"
        classes["neo4jlabs"] = classes["pc_v1_1"] = "RUNNABLE_UNCHANGED"  # secondaries never count
        self.assertEqual(R.import_gate(classes), ("FAIL", 3))

    def test_gate_threshold_is_fixed_at_four(self):
        self.assertEqual(R.GATE_THRESHOLD, 4)


class TestIsolation(unittest.TestCase):
    def test_network_blocked_in_runner(self):
        code = ("import sys; sys.argv=['x']; sys.path.insert(0, %r); import run_adapter, socket\n"
                "try:\n    socket.create_connection(('example.com', 80)); print('OPEN')\n"
                "except run_adapter.NetworkBlocked: print('BLOCKED')" % CODE)
        p = subprocess.run([PY, "-c", code], capture_output=True, text=True, timeout=60)
        self.assertIn("BLOCKED", p.stdout)

    def test_runner_refuses_non_smoke_fixture(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"fixture_id": "audit-s1-v1", "cases": []}, f)
        p, rec = run_adapter("pipecypher", fixture=f.name)
        os.unlink(f.name)
        self.assertIsNone(rec)
        self.assertIn("refused", p.stderr + p.stdout)

    def test_smoke_fixture_is_not_s1(self):
        fx = json.load(open(SMOKE))
        self.assertEqual(fx["fixture_id"], "audit-smoke-v1")
        self.assertTrue(all(c["case_id"].startswith("SMOKE-") for c in fx["cases"]))

    def test_s1_not_referenced_by_adapters_or_tests(self):
        for fn in ["audit_adapters.py", "run_adapter.py"]:
            self.assertNotIn("s1_cases", open(os.path.join(CODE, fn)).read(), fn)
        # audit_readiness.py may reference S1 only to hash it (integrity: proves S1 untouched), never to load cases
        src = open(os.path.join(CODE, "audit_readiness.py")).read()
        self.assertEqual(src.count("s1_cases.jsonl"), 1)
        self.assertNotIn("json.loads(line", src)


if __name__ == "__main__":
    unittest.main()
