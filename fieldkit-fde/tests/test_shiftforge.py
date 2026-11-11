import copy
import unittest

from fieldkit.projects.shiftforge import SAMPLE, run


def fixture():
    return {"horizon_minutes": 100, "machines": [{"id": "m1", "skills": ["cut"]}], "jobs": [{"id": "a", "skill": "cut", "duration_minutes": 20, "due_minute": 30, "depends_on": []}]}


class ShiftForgeTests(unittest.TestCase):
    def test_sample_surfaces_missing_skill(self):
        result = run(copy.deepcopy(SAMPLE))
        self.assertEqual(result["metrics"]["scheduled_jobs"], 6)
        self.assertEqual(result["unscheduled"][0]["reason"], "missing_machine_skill")
        self.assertEqual(result["unscheduled"][0]["job"], "C-coat")

    def test_machine_jobs_do_not_overlap(self):
        result = run(copy.deepcopy(SAMPLE))
        for machine in result["machines"]:
            records = sorted((r for r in result["records"] if r["machine"] == machine["machine"]), key=lambda r: r["start_minute"])
            for left, right in zip(records, records[1:]):
                self.assertLessEqual(left["end_minute"], right["start_minute"])
            self.assertLessEqual(machine["busy_minutes"], machine["available_minutes"])

    def test_dependencies_finish_before_successor_starts(self):
        records = {r["job"]: r for r in run(copy.deepcopy(SAMPLE))["records"]}
        for row in records.values():
            for dependency in row["depends_on"]:
                self.assertGreaterEqual(row["start_minute"], records[dependency]["end_minute"])

    def test_nonpreemptive_job_skips_maintenance(self):
        value = fixture()
        value["machines"][0]["unavailable"] = [{"start": 10, "end": 30}]
        row = run(value)["records"][0]
        self.assertEqual(row["start_minute"], 30)
        self.assertEqual(row["end_minute"], 50)
        self.assertEqual(row["late_minutes"], 20)

    def test_boundary_finish_before_maintenance_allowed(self):
        value = fixture()
        value["machines"][0]["unavailable"] = [{"start": 20, "end": 30}]
        self.assertEqual(run(value)["records"][0]["start_minute"], 0)

    def test_rejected_dependency_blocks_successor(self):
        value = fixture()
        value["jobs"][0]["skill"] = "weld"
        value["jobs"].append({"id": "b", "skill": "cut", "duration_minutes": 10, "due_minute": 60, "depends_on": ["a"]})
        result = run(value)
        self.assertEqual(result["metrics"]["scheduled_jobs"], 0)
        reasons = {r["job"]: r for r in result["unscheduled"]}
        self.assertEqual(reasons["b"]["reason"], "blocked_dependency")
        self.assertEqual(reasons["b"]["dependencies"], ["a"])

    def test_cycle_rejected(self):
        value = fixture()
        value["jobs"][0]["depends_on"] = ["b"]
        value["jobs"].append({"id": "b", "skill": "cut", "duration_minutes": 10, "depends_on": ["a"]})
        with self.assertRaisesRegex(ValueError, "cycle"):
            run(value)

    def test_unknown_dependency_rejected(self):
        value = fixture()
        value["jobs"][0]["depends_on"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "Unknown dependency"):
            run(value)

    def test_horizon_is_hard_constraint(self):
        value = fixture()
        value["horizon_minutes"] = 10
        result = run(value)
        self.assertEqual(result["metrics"]["scheduled_jobs"], 0)
        self.assertEqual(result["unscheduled"][0]["reason"], "planning_horizon_capacity")

    def test_release_and_machine_availability_respected(self):
        value = fixture()
        value["machines"][0]["available_from"] = 30
        value["jobs"][0]["release_minute"] = 40
        self.assertEqual(run(value)["records"][0]["start_minute"], 40)

    def test_overlapping_maintenance_and_invalid_duration_rejected(self):
        value = fixture()
        value["machines"][0]["unavailable"] = [{"start": 10, "end": 30}, {"start": 20, "end": 40}]
        with self.assertRaises(ValueError):
            run(value)
        for duration in [0, -1, True, float("nan")]:
            value = fixture()
            value["jobs"][0]["duration_minutes"] = duration
            with self.assertRaises(ValueError):
                run(value)

    def test_empty_jobs_has_zero_makespan(self):
        value = fixture()
        value["jobs"] = []
        self.assertEqual(run(value)["metrics"]["makespan_minutes"], 0)


if __name__ == "__main__":
    unittest.main()
