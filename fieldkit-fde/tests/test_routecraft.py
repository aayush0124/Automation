import copy
import unittest

from fieldkit.projects.routecraft import SAMPLE, run


def fixture():
    return {"depot": [0, 0], "vehicles": [{"id": "van", "capacity": 4, "shift_start": 0, "shift_end": 50, "speed_units_per_minute": 1}], "jobs": [{"id": "one", "location": [3, 4], "demand": 2, "window_start": 0, "window_end": 20, "service_minutes": 5}]}


class RouteCraftTests(unittest.TestCase):
    def test_sample_explains_impossible_jobs(self):
        result = run(copy.deepcopy(SAMPLE))
        self.assertEqual(result["metrics"]["assigned_jobs"], 4)
        by_id = {row["job"]: row for row in result["unassigned"]}
        self.assertIn("capacity", by_id["wholesaler"]["single_job_constraint_evidence"])
        self.assertIn("service_completion_window", by_id["distant-kiosk"]["single_job_constraint_evidence"])

    def test_geometry_service_and_return_are_computed(self):
        result = run(fixture())
        route = result["routes"][0]
        self.assertEqual(route["distance_units"], 10)
        self.assertEqual(route["return_minute"], 15)
        self.assertEqual(route["stops"][0]["arrival_minute"], 5)
        self.assertEqual(route["stops"][0]["service_end_minute"], 10)

    def test_completion_not_just_arrival_must_fit_window(self):
        value = fixture()
        value["jobs"][0]["window_end"] = 9
        self.assertEqual(run(value)["metrics"]["assigned_jobs"], 0)

    def test_return_to_depot_must_fit_shift(self):
        value = fixture()
        value["vehicles"][0]["shift_end"] = 14
        result = run(value)
        self.assertEqual(result["metrics"]["assigned_jobs"], 0)
        self.assertIn("return_to_depot_after_shift", result["unassigned"][0]["constraint_evidence"])

    def test_capacity_is_total_delivery_load(self):
        value = fixture()
        value["jobs"].append({**value["jobs"][0], "id": "two", "demand": 3})
        result = run(value)
        self.assertEqual(result["metrics"]["assigned_jobs"], 1)
        self.assertEqual(result["unassigned"][0]["reason"], "fleet_commitments_prevent_insertion")
        self.assertLessEqual(result["routes"][0]["load"], 4)

    def test_early_arrival_waits_for_window(self):
        value = fixture()
        value["jobs"][0]["window_start"] = 12
        stop = run(value)["records"][0]
        self.assertEqual(stop["wait_minutes"], 7)
        self.assertEqual(stop["service_start_minute"], 12)

    def test_empty_jobs_produces_idle_routes(self):
        value = fixture()
        value["jobs"] = []
        result = run(value)
        self.assertEqual(result["records"], [])
        self.assertEqual(result["metrics"]["distance_units"], 0)

    def test_deadline_order_can_recover_input_order_failure(self):
        value = fixture()
        value["jobs"] = [
            {"id": "late", "location": [10, 0], "demand": 1, "window_start": 0, "window_end": 40, "service_minutes": 2},
            {"id": "urgent", "location": [1, 0], "demand": 1, "window_start": 0, "window_end": 4, "service_minutes": 1},
        ]
        result = run(value)
        self.assertEqual(result["metrics"]["assigned_jobs"], 2)
        self.assertEqual(result["metrics"]["baseline_assigned_jobs"], 1)
        self.assertFalse(result["comparison"]["distance_comparable"])

    def test_bad_input_rejected(self):
        mutations = [
            lambda p: p["vehicles"][0].update(speed_units_per_minute=0),
            lambda p: p["jobs"][0].update(location=[float("nan"), 0]),
            lambda p: p["jobs"][0].update(demand=-1),
            lambda p: p["jobs"].append(copy.deepcopy(p["jobs"][0])),
            lambda p: p.update(vehicles=[]),
        ]
        for mutate in mutations:
            value = fixture()
            mutate(value)
            with self.assertRaises(ValueError):
                run(value)

    def test_equal_counts_different_jobs_are_not_distance_comparable(self):
        value = fixture()
        value["vehicles"][0]["capacity"] = 1
        value["jobs"] = [
            {"id": "far", "location": [10, 0], "demand": 1, "window_start": 0, "window_end": 40, "service_minutes": 2},
            {"id": "urgent", "location": [1, 0], "demand": 1, "window_start": 0, "window_end": 4, "service_minutes": 1},
        ]
        result = run(value)
        self.assertEqual(result["metrics"]["assigned_jobs"], result["metrics"]["baseline_assigned_jobs"])
        self.assertFalse(result["comparison"]["distance_comparable"])

    def test_no_job_duplicated_across_vehicles(self):
        result = run(copy.deepcopy(SAMPLE))
        assigned = [row["job"] for row in result["records"]]
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertTrue(all(route["load"] <= route["capacity"] for route in result["routes"]))


if __name__ == "__main__":
    unittest.main()
