import copy
import json
import unittest

from fieldkit.projects.launchgate import SAMPLE, percentile, run


def healthy():
    payload = copy.deepcopy(SAMPLE)
    payload["canary"] = {"requests": 400, "errors": 1, "window_minutes": 10, "latency_ms": [100] * 20}
    payload["baseline"]["latency_ms"] = [100] * 20
    return payload


class LaunchGateTests(unittest.TestCase):
    def test_sample_fails_measured_canary_gates(self):
        result = run(copy.deepcopy(SAMPLE))
        self.assertEqual(result["decision"], "rollback")
        self.assertAlmostEqual(result["canary"]["burn_rate"], 3.5)
        self.assertEqual(result["canary"]["p95_ms"], 420)
        self.assertIn("p95 latency ratio", result["failures"])
        json.dumps(result, allow_nan=False)

    def test_healthy_evidence_approves_next_stage(self):
        result = run(healthy())
        self.assertEqual(result["decision"], "approve")
        self.assertEqual(result["metrics"]["passed_checks"], 7)

    def test_zero_traffic_holds_and_never_divides_by_zero(self):
        payload = healthy()
        payload["canary"] = {"requests": 0, "errors": 0, "window_minutes": 10, "latency_ms": []}
        result = run(payload)
        self.assertEqual(result["decision"], "hold")
        self.assertIsNone(result["canary"]["error_rate"])
        self.assertIsNone(result["canary"]["burn_rate"])

    def test_small_cohort_holds_even_if_observed_errors_high(self):
        payload = healthy()
        payload["canary"] = {"requests": 1, "errors": 1, "window_minutes": 10, "latency_ms": [100]}
        self.assertEqual(run(payload)["decision"], "hold")

    def test_missing_latency_cannot_approve(self):
        payload = healthy()
        payload["canary"]["latency_ms"] = []
        self.assertEqual(run(payload)["decision"], "hold")

    def test_measured_error_failure_can_rollback_without_latency_data(self):
        payload = healthy()
        payload["canary"]["errors"] = 100
        payload["canary"]["latency_ms"] = []
        self.assertEqual(run(payload)["decision"], "rollback")

    def test_nonmatching_windows_hold_relative_comparisons(self):
        payload = healthy()
        payload["canary"]["window_minutes"] = 5
        result = run(payload)
        self.assertEqual(result["decision"], "hold")
        self.assertIn("Comparable windows", result["holds"])

    def test_zero_baseline_latency_does_not_invent_ratio(self):
        payload = healthy()
        payload["baseline"]["latency_ms"] = [0] * 20
        self.assertEqual(run(payload)["decision"], "hold")

    def test_nearest_rank_percentile_has_documented_small_sample_behavior(self):
        self.assertEqual(percentile(list(range(1, 21)), .95), 19)
        self.assertEqual(percentile([10], .95), 10)
        self.assertIsNone(percentile([], .95))

    def test_percentage_points_not_relative_percentage(self):
        payload = healthy()
        payload["canary"]["errors"] = 5  # 1.25% versus baseline 0.25% = 1 pp, boundary passes.
        result = run(payload)
        row = next(r for r in result["records"] if r["check"].startswith("Error regression"))
        self.assertAlmostEqual(row["observed"], 1)
        self.assertEqual(row["outcome"], "pass")

    def test_budget_projection_uses_minutes_and_period(self):
        payload = healthy()
        payload["canary"]["errors"] = 4  # 1% error rate = burn 1.
        result = run(payload)
        self.assertAlmostEqual(result["canary"]["projected_budget_consumption_percent"], 10 / (30 * 1440) * 100, places=6)

    def test_invalid_numeric_and_unit_inputs_rejected(self):
        changes = [("requests", True), ("errors", 401), ("window_minutes", 0), ("latency_ms", [float("nan")]),
                   ("latency_ms", [-1]), ("latency_ms", [float("inf")]), ("latency_ms", "100ms")]
        for key, value in changes:
            payload = healthy()
            payload["canary"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                run(payload)

    def test_invalid_policy_rejected(self):
        for policy in ({"success_slo": 1}, {"max_burn_rate": float("nan")}, {"min_requests": 0}, {"max_latency_seconds": 1}):
            payload = healthy()
            payload["policy"] = policy
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                run(payload)

    def test_more_latency_samples_than_requests_rejected(self):
        payload = healthy()
        payload["canary"]["latency_ms"] = [1] * 401
        with self.assertRaises(ValueError):
            run(payload)


if __name__ == "__main__":
    unittest.main()
