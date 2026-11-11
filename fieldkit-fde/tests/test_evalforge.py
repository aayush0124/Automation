import copy
import math
import unittest

from fieldkit.projects import evalforge


class EvalForgeTests(unittest.TestCase):
    def setUp(self):
        self.payload = copy.deepcopy(evalforge.SAMPLE)

    def test_sample_computes_paired_improvement(self):
        result = evalforge.run(self.payload)
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["metrics"]["paired_wins"], 2)
        self.assertEqual(result["metrics"]["paired_losses"], 0)
        self.assertEqual(result["metrics"]["candidate_pass_rate"], 1)
        self.assertLess(result["uncertainty"]["candidate_pass_rate_95_interval"][0], 0.7)

    def test_critical_regression_blocks_even_when_aggregate_gate_relaxed(self):
        self.payload["candidate"][0]["output"] = "90 days"
        self.payload["thresholds"]["min_pass_rate"] = 0.5
        result = evalforge.run(self.payload)
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["critical_failure_ids"], ["refund-window"])

    def test_missing_and_extra_cases_are_rejected_not_silently_dropped(self):
        self.payload["candidate"][-1]["case_id"] = "unknown"
        with self.assertRaisesRegex(ValueError, "alignment"):
            evalforge.run(self.payload)

    def test_duplicate_case_rejected(self):
        self.payload["baseline"].append(copy.deepcopy(self.payload["baseline"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            evalforge.run(self.payload)

    def test_extra_citation_is_a_failure(self):
        self.payload["candidate"][0]["citations"].append("invented-policy")
        result = evalforge.run(self.payload)
        self.assertFalse(result["records"][0]["candidate_pass"])
        self.assertIn("Unapproved citations", result["records"][0]["candidate_failures"][0])

    def test_abstention_cannot_hide_an_answer(self):
        self.payload["candidate"][3]["output"] = "Private customer balance"
        result = evalforge.run(self.payload)
        self.assertIn("private-account", result["critical_failure_ids"])

    def test_zero_baseline_cost_with_positive_candidate_holds(self):
        for row in self.payload["baseline"]:
            row["cost_usd"] = 0
        result = evalforge.run(self.payload)
        self.assertIsNone(result["metrics"]["mean_cost_ratio"])
        self.assertEqual(result["decision"], "HOLD")

    def test_zero_cost_both_sides_is_neutral(self):
        for arm in ("baseline", "candidate"):
            for row in self.payload[arm]:
                row["cost_usd"] = 0
        self.assertEqual(evalforge.run(self.payload)["metrics"]["mean_cost_ratio"], 1)

    def test_extremely_small_baseline_cannot_emit_infinity(self):
        for row in self.payload["baseline"]:
            row["cost_usd"] = 1e-323
        result = evalforge.run(self.payload)
        self.assertIsNone(result["metrics"]["mean_cost_ratio"])
        self.assertEqual(result["decision"], "HOLD")

    def test_latency_budget_blocks_good_answers(self):
        for row in self.payload["candidate"]:
            row["latency_ms"] = 10000
        result = evalforge.run(self.payload)
        self.assertEqual(result["decision"], "HOLD")
        self.assertFalse(next(g for g in result["gates"] if g["gate"] == "mean_latency_ratio")["passed"])

    def test_result_order_does_not_change_pairing(self):
        original = evalforge.run(self.payload)
        self.payload["candidate"].reverse()
        self.assertEqual(original, evalforge.run(self.payload))

    def test_nan_and_boolean_measurements_rejected(self):
        for bad in (math.nan, math.inf, -1, True, 10 ** 1000):
            with self.subTest(value=bad):
                data = copy.deepcopy(self.payload)
                data["candidate"][0]["latency_ms"] = bad
                with self.assertRaises(ValueError):
                    evalforge.run(data)

    def test_threshold_typo_and_fractional_minimum_rejected(self):
        self.payload["thresholds"]["min_passrate"] = 0.2
        with self.assertRaisesRegex(ValueError, "Unknown threshold"):
            evalforge.run(self.payload)
        del self.payload["thresholds"]["min_passrate"]
        self.payload["thresholds"]["min_cases"] = 2.5
        with self.assertRaisesRegex(ValueError, "integer"):
            evalforge.run(self.payload)

    def test_small_sample_holds_when_minimum_is_raised(self):
        self.payload["thresholds"]["min_cases"] = 100
        result = evalforge.run(self.payload)
        self.assertEqual(result["decision"], "HOLD")
        self.assertTrue(any("Small evaluation set" in w for w in result["warnings"]))

    def test_exact_sign_test_known_values(self):
        self.assertAlmostEqual(evalforge._sign_test(5, 0), 0.0625)
        self.assertEqual(evalforge._sign_test(0, 0), 1)
        self.assertAlmostEqual(evalforge._sign_test(3, 3), 1)

    def test_no_semantic_equivalence_claim(self):
        self.payload["candidate"][0]["output"] = "Thirty days"
        result = evalforge.run(self.payload)
        self.assertFalse(result["records"][0]["candidate_pass"])


if __name__ == "__main__":
    unittest.main()
