import copy
import unittest

from fieldkit.projects.switchboard import SAMPLE, run


class SwitchboardTests(unittest.TestCase):
    def test_database_outage_ranks_above_downstream_symptoms(self):
        result = run(copy.deepcopy(SAMPLE))
        self.assertEqual(result["records"][0]["service"], "database")
        self.assertEqual(result["records"][0]["alerting_dependents"], ["checkout", "orders", "payments"])
        self.assertEqual(result["mode"], "dry_run")
        self.assertTrue(all(p["status"] == "review_required" for p in result["response_plan"]))

    def test_unrelated_service_is_not_in_blast_radius(self):
        result = run(copy.deepcopy(SAMPLE))
        database = next(r for r in result["records"] if r["service"] == "database")
        self.assertNotIn("catalog", database["potentially_affected_services"])
        self.assertNotIn("cache", database["potentially_affected_services"])

    def test_dependency_cycle_terminates_without_self_impact(self):
        value = {"services": [{"id": "a", "depends_on": ["b"], "error_rate_pct": 10}, {"id": "b", "depends_on": ["a"], "error_rate_pct": 20}]}
        result = run(value)
        self.assertEqual(result["metrics"]["cycle_edges"], 1)
        for record in result["records"]:
            self.assertNotIn(record["service"], record["potentially_affected_services"])
            self.assertEqual(len(record["potentially_affected_services"]), 1)

    def test_future_and_old_deployments_are_not_correlation_evidence(self):
        value = copy.deepcopy(SAMPLE)
        value["deployments"] = [{"service": "database", "minute": 601, "version": "future"}, {"service": "database", "minute": 569, "version": "old"}]
        result = run(value)
        self.assertEqual(result["metrics"]["recent_deployments"], 0)
        self.assertTrue(any("future" in warning for warning in result["warnings"]))

    def test_boundary_deployment_is_included(self):
        value = copy.deepcopy(SAMPLE)
        value["deployments"][0]["minute"] = 570
        self.assertEqual(run(value)["metrics"]["recent_deployments"], 1)

    def test_healthy_graph_has_no_remediation_plan(self):
        value = copy.deepcopy(SAMPLE)
        for service in value["services"]:
            service["error_rate_pct"] = 0
        result = run(value)
        self.assertEqual(result["records"], [])
        self.assertEqual(result["response_plan"], [])

    def test_unknown_dependency_fails(self):
        value = copy.deepcopy(SAMPLE)
        value["services"][0]["depends_on"].append("missing")
        with self.assertRaisesRegex(ValueError, "Unknown dependency"):
            run(value)

    def test_duplicate_service_rejected(self):
        value = copy.deepcopy(SAMPLE)
        value["services"].append(value["services"][0])
        with self.assertRaisesRegex(ValueError, "Duplicate service"):
            run(value)

    def test_invalid_error_rates_rejected(self):
        for bad in [float("nan"), float("inf"), -1, 101, True, "10"]:
            with self.subTest(bad=bad):
                value = copy.deepcopy(SAMPLE)
                value["services"][0]["error_rate_pct"] = bad
                with self.assertRaises(ValueError):
                    run(value)

    def test_input_not_mutated_and_order_stable(self):
        value = copy.deepcopy(SAMPLE)
        before = copy.deepcopy(value)
        first = run(value)
        self.assertEqual(value, before)
        self.assertEqual(first, run(value))


if __name__ == "__main__":
    unittest.main()
