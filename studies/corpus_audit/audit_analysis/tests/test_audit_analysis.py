"""the main audit run MAIN_AUDIT analysis tests — SYNTHETIC data only (no S1/S2/S3 verdicts are used to debug statistics)."""
import hashlib
import json
import math
import os
import stat
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.join(HERE, "..", "code")
sys.path.insert(0, CODE)
import audit_analysis as K  # noqa: E402
import build_pairs as BP  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))


def synth(units, assign):
    """units: n; assign(i, scorer) -> verdict."""
    return {f"u{i}": {s: assign(i, s) for s in K.PRIMARY + K.SECONDARY} for i in range(units)}


class TestFrozenInputs(unittest.TestCase):
    def test_s1_hash_and_counts(self):
        p = os.path.join(ROOT, "studies", "controlled_suite", "audit", "s1", "s1_cases.jsonl")
        self.assertEqual(hashlib.sha256(open(p, "rb").read()).hexdigest(),
                         "80d0fd3fa181470fb5d59c0fbeea9cf748e1cd2bcc3ade61e4387118a17d5b47")

    def test_scorer_count_and_pairs(self):
        self.assertEqual(len(K.PRIMARY), 7)
        self.assertEqual(len(K.pairs_of(K.PRIMARY)), 21)
        self.assertEqual(K.N_HYPOTHESES, 21)
        self.assertTrue(set(K.SECONDARY).isdisjoint(K.PRIMARY))


class TestStatistics(unittest.TestCase):
    def test_wilson_known_values(self):
        lo, hi = K.wilson(0, 10, 1.959963984540054)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.27753, places=4)
        lo, hi = K.wilson(5, 10, 1.959963984540054)
        self.assertAlmostEqual(lo, 0.23659, places=4)
        self.assertAlmostEqual(hi, 0.76341, places=4)
        self.assertEqual(K.wilson(0, 0, 1.96), (None, None))

    def test_bonferroni_constants(self):
        self.assertAlmostEqual(K.PER_COMPARISON_ALPHA, 0.05 / 21)
        self.assertAlmostEqual(K.Z_BONF_ONE_SIDED, 2.8227, places=3)
        self.assertEqual(K.H_THRESHOLD, 0.02)

    def test_exact_mcnemar(self):
        self.assertAlmostEqual(K.exact_mcnemar(0, 5), 0.0625)
        self.assertEqual(K.exact_mcnemar(0, 0), 1.0)
        self.assertAlmostEqual(K.exact_mcnemar(3, 3), 1.0)

    def test_pairwise_denominator_excludes_errors(self):
        v = synth(10, lambda i, s: ("ERROR:X" if (s == "cypherturn" and i < 2) else
                                    (1 if (s == "cypherbench" and i == 5) else 0)))
        rows = {(r["scorer_a"], r["scorer_b"]): r for r in K.pairwise(v)}
        r = rows[("cypherturn", "cypherbench")]
        self.assertEqual((r["n"], r["excluded_error"], r["disagreements"]), (8, 2, 1))
        r0 = {(x["scorer_a"], x["scorer_b"]): x for x in K.pairwise(v, error_as_zero=True)}[("cypherturn", "cypherbench")]
        self.assertEqual((r0["n"], r0["disagreements"]), (10, 1))

    def test_h1_threshold_both_sides(self):
        # 40/400 disagreements: one-sided Bonferroni lower bound well above 0.02 -> SUPPORTED
        v = synth(400, lambda i, s: 1 if (s == "pipecypher" and i < 40) else 0)
        self.assertTrue(K.h1_decision(K.pairwise(v))["supported"])
        # 4/400: rate 1% -> lower bound < 0.02 -> NOT SUPPORTED
        v = synth(400, lambda i, s: 1 if (s == "pipecypher" and i < 4) else 0)
        d = K.h1_decision(K.pairwise(v))
        self.assertFalse(d["supported"])
        self.assertLess(d["max_lower_bound"], 0.02)

    def test_h1_boundary_is_unrounded(self):
        # find k such that the lower bound straddles 0.02 at n=563 and check exact >= comparison
        n = 563
        ks = [k for k in range(n) if K.wilson_lower_one_sided(k, n) >= 0.02]
        kmin = ks[0]
        self.assertLess(K.wilson_lower_one_sided(kmin - 1, n), 0.02)
        v = {f"u{i}": {s: (1 if (s == "tugraph" and i < kmin) else 0) for s in K.PRIMARY + K.SECONDARY}
             for i in range(n)}
        self.assertTrue(K.h1_decision(K.pairwise(v))["supported"])
        v = {f"u{i}": {s: (1 if (s == "tugraph" and i < kmin - 1) else 0) for s in K.PRIMARY + K.SECONDARY}
             for i in range(n)}
        self.assertFalse(K.h1_decision(K.pairwise(v))["supported"])

    def test_secondary_scorers_excluded_from_h1(self):
        v = synth(400, lambda i, s: 1 if (s in K.SECONDARY and i < 200) else 0)
        d = K.h1_decision(K.pairwise(v))
        self.assertFalse(d["supported"])
        self.assertEqual(d["max_rate"], 0)
        self.assertEqual(d["n_pairs"], 21)

    def test_unanimity_and_marginals(self):
        v = synth(6, lambda i, s: 1 if (i < 2 or (i == 2 and s == "cyspider")) else 0)
        u = K.unanimity(v)
        self.assertEqual((u["unanimous"], u["at_least_one_disagreement"], u["unanimous_pass"]), (5, 1, 2))
        m = K.marginals(v, ["cyspider"])["cyspider"]
        self.assertEqual((m["n"], m["pass"]), (6, 3))

    def test_cluster_bootstrap_deterministic(self):
        v = synth(30, lambda i, s: 1 if (s == "cyspider" and i % 3 == 0) else 0)
        cl = {u: f"c{int(u[1:]) // 2}" for u in v}
        a = K.cluster_bootstrap_pairwise(v, cl, B=200)
        b = K.cluster_bootstrap_pairwise(v, cl, B=200)
        self.assertEqual(a, b)

    def test_s1_intent_dependent_excluded_from_oracle_accuracy(self):
        cases = {"c1": {"expected": "EQUIV", "dimension": "D1"}, "c2": {"expected": "NONEQUIV", "dimension": "D2"},
                 "c3": {"expected": "INTENT_DEPENDENT", "dimension": "D3"}}
        v = {"c1": {"x": 1}, "c2": {"x": 1}, "c3": {"x": 1}}
        sc, dim, intent = K.s1_oracle(v, cases, ["x"])
        self.assertEqual((sc["x"]["n_oracle_defined"], sc["x"]["correct"], sc["x"]["incorrect"]), (2, 1, 1))
        self.assertNotIn("D3", dim)
        self.assertEqual(intent["x"]["D3"], [1])

    def test_s1_error_counts_as_incorrect_and_reported(self):
        cases = {"c1": {"expected": "EQUIV", "dimension": "D1"}}
        sc, _, _ = K.s1_oracle({"c1": {"x": "ERROR:TypeError"}}, cases, ["x"])
        self.assertEqual((sc["x"]["incorrect"], sc["x"]["errors"]), (1, 1))

    def test_features_mechanical(self):
        pair = {"reference": {"query": "MATCH ... ORDER BY x", "columns": ["a"], "rows": [[1], [2]]},
                "prediction": {"query": "SELECT ...", "columns": ["b"], "rows": [[2.0], [1.0]]}}
        f = K.features(pair)
        self.assertIn("key_name_difference", f)
        self.assertIn("order_by_in_reference", f)
        self.assertIn("int_float_type_difference", f)
        pair2 = {"reference": {"query": "q", "columns": ["a"], "rows": [[1], [1]]},
                 "prediction": {"query": "p", "columns": ["a"], "rows": [[1]]}}
        self.assertEqual(K.features(pair2), ["multiplicity_difference"])  # same row set, different multiset
        pair3 = {"reference": {"query": "q", "columns": ["a"], "rows": [[1], [1], [2]]},
                 "prediction": {"query": "p", "columns": ["a"], "rows": [[1], [2], [2]]}}
        self.assertIn("multiplicity_difference", K.features(pair3))


class TestPairConstruction(unittest.TestCase):
    def test_build_s3_no_exclusions_and_order(self):
        ds = [{"question": "q1", "cypher": "C1", "SQL": "S1", "neo4j_output": [{"b": 1, "a": 2}], "sql_output": [{"a": 2, "b": 1}]},
              {"question": "q2", "cypher": "C2", "SQL": "S2", "neo4j_output": [], "sql_output": []},
              {"question": "q3", "cypher": "C3", "SQL": "S3", "neo4j_output": None, "sql_output": []}]
        s3 = BP.build_s3(ds)
        self.assertEqual([p["case_id"] for p in s3], ["S3-000", "S3-001"])
        self.assertEqual(s3[0]["reference"]["columns"], ["b", "a"])
        self.assertEqual(s3[0]["prediction"]["columns"], ["a", "b"])
        self.assertTrue(s3[1]["meta"]["empty_reference"])

    def test_inconsistent_keys_raise(self):
        with self.assertRaises(ValueError):
            BP.side_from_dicts("q", [{"a": 1}, {"b": 2}])

    def test_s1_conversion_is_representation_only(self):
        import run_experiment as RE
        c = {"case_id": "X", "ref_query": "r", "pred_query": "p", "ref_columns": ["n", "m"], "pred_columns": ["m"],
             "reference_result": [{"n": 1, "m": None}], "predicted_result": [{"m": 1.0}, {"m": 1.0}]}
        p = RE.s1_to_pair(c)
        self.assertEqual(p["reference"], {"query": "r", "columns": ["n", "m"], "rows": [[1, None]]})
        self.assertEqual(p["prediction"]["rows"], [[1.0], [1.0]])


class TestExecutionGuards(unittest.TestCase):
    def test_run_all_refuses_existing_raw(self):
        import run_all as RA
        orig = RA.check_freeze
        RA.check_freeze = lambda: {"freeze_sha256": "x", "files_sha256": {}}
        try:
            with tempfile.TemporaryDirectory() as d:
                os.makedirs(os.path.join(d, "raw"))
                sys.argv = ["run_all.py", d]
                with self.assertRaises(SystemExit) as cm:
                    RA.main()
                self.assertIn("already exists", str(cm.exception))
        finally:
            RA.check_freeze = orig

    def test_raw_files_read_only_after_chmod(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.jsonl")
            open(p, "w").write("{}\n")
            os.chmod(p, 0o444)
            self.assertFalse(os.stat(p).st_mode & stat.S_IWUSR)

    def test_output_parsing_deterministic(self):
        import compute_stats as CS
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "raw", "s9"))
            for s in CS.ALL:
                with open(os.path.join(d, "raw", "s9", f"{s}.jsonl"), "w") as f:
                    f.write(json.dumps({"case_id": "a", "scorer": s, "native": "1.0", "verdict": 1}) + "\n")
                    f.write(json.dumps({"case_id": "b", "scorer": s, "native": None, "verdict": "ERROR:X"}) + "\n")
            v1, _ = CS.load_verdicts(d, "s9")
            v2, _ = CS.load_verdicts(d, "s9")
            self.assertEqual(v1, v2)
            self.assertEqual(v1["b"]["cypherturn"], "ERROR:X")
            self.assertFalse(K.is_binary(v1["b"]["cypherturn"]))
            self.assertTrue(K.is_binary(v1["a"]["cypherturn"]))


if __name__ == "__main__":
    unittest.main()


class TestEndToEndSynthetic(unittest.TestCase):
    def test_compute_stats_runs_on_synthetic_raw(self):
        """Full compute_stats pipeline (tables, trace, figures) on SYNTHETIC verdicts; S1 used only for case ids /
        labels, never scorer outputs."""
        import random as _r
        import subprocess
        import compute_stats as CS
        rng = _r.Random(0)
        s1_ids = [json.loads(l)["case_id"] for l in open(CS.S1)]
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "pairs"))
            mk = lambda cid, q: {"case_id": cid, "reference": {"query": q, "columns": ["a"], "rows": [[1], [2]]},
                                 "prediction": {"query": "p", "columns": ["b"], "rows": [[2.0], [1.0]]},
                                 "meta": {"cluster": cid[:6], "model": "m", "empty_prediction": False}}
            sets = {"s1": s1_ids, "s3": [f"S3-{i:03d}" for i in range(40)], "s2": [f"S2-m|Q{i}" for i in range(20)]}
            for name in ["s3", "s2"]:
                with open(os.path.join(d, "pairs", f"{name}_pairs.jsonl"), "w") as f:
                    for cid in sets[name]:
                        f.write(json.dumps(mk(cid, "MATCH ORDER BY x")) + "\n")
            for name, ids in sets.items():
                os.makedirs(os.path.join(d, "raw", name))
                for s in CS.ALL:
                    with open(os.path.join(d, "raw", name, f"{s}.jsonl"), "w") as f:
                        for cid in ids:
                            v = rng.choice([0, 1, 1, "ERROR:TypeError"]) if s == "cyspider" else rng.choice([0, 1])
                            f.write(json.dumps({"case_id": cid, "scorer": s, "native": str(v), "verdict": v}) + "\n")
            p = subprocess.run([sys.executable, os.path.join(CODE, "compute_stats.py"), d], capture_output=True,
                               text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), timeout=600)
            self.assertEqual(p.returncode, 0, p.stderr[-2000:])
            for fn in ["s1_results.csv", "s1_dimension_summary.csv", "s3_results.csv", "s3_pairwise_disagreement.csv",
                       "s2_results.csv", "secondary_scorer_results.csv", "audit_statistics.json", "audit_decision_trace.json",
                       "figures/fig1_s3_disagreement_heatmap.png", "figures/fig2_s1_dimension_matrix.png",
                       "figures/fig3_s3_pairwise_rates_ci.png"]:
                self.assertTrue(os.path.exists(os.path.join(d, fn)), fn)
            t = json.load(open(os.path.join(d, "audit_decision_trace.json")))
            self.assertEqual(t["pairwise_comparisons"], 21)
            self.assertEqual(t["final_topic_decision"].split()[0], "REQUIRES_HUMAN_INTERPRETATION")
