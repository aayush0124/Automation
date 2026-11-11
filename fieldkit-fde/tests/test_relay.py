import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fieldkit.projects.relay import RelayStore, SAMPLE, run


def event(key="one", tenant="a", version=1, failures=0):
    return {"tenant": tenant, "key": key, "aggregate": "order", "version": version,
            "body": {"state": f"v{version}"}, "failures_before_success": failures}


class RelayTests(unittest.TestCase):
    def test_sample_reports_measured_counts(self):
        result = run(copy.deepcopy(SAMPLE))
        self.assertEqual(result["metrics"]["delivered"], 3)
        self.assertEqual(result["metrics"]["duplicates"], 1)
        self.assertEqual(result["metrics"]["dead_letters"], 1)
        self.assertEqual(result["metrics"]["pending"], 0)
        json.dumps(result, allow_nan=False)

    def test_duplicate_does_not_apply_twice(self):
        result = run({"events": [event(), event()], "ticks": [0, 1]})
        self.assertEqual(result["metrics"]["unique_events"], 1)
        self.assertEqual(result["metrics"]["delivery_attempts"], 1)
        self.assertEqual(len(result["states"]), 1)

    def test_same_key_different_tenants_remains_isolated(self):
        result = run({"events": [event(tenant="a"), event(tenant="b")]})
        self.assertEqual(result["metrics"]["delivered"], 2)
        self.assertEqual({s["tenant"] for s in result["states"]}, {"a", "b"})

    def test_conflicting_payload_is_rejected_without_overwrite(self):
        changed = event()
        changed["body"] = {"state": "forged"}
        result = run({"events": [event(), changed]})
        self.assertEqual(result["metrics"]["conflicts"], 1)
        self.assertEqual(result["states"][0]["body"], {"state": "v1"})

    def test_hash_is_independent_of_object_key_order(self):
        a, b = event(), event()
        a["body"] = {"first": 1, "second": 2}
        b["body"] = {"second": 2, "first": 1}
        self.assertEqual(run({"events": [a, b]})["metrics"]["duplicates"], 1)

    def test_out_of_order_and_transient_failure_preserve_sequence(self):
        result = run({"events": [event("two", version=2), event(failures=1)], "ticks": [0, 1, 2]})
        deliveries = [r["version"] for r in result["trace"] if r["status"] == "delivered"]
        self.assertEqual(deliveries, [1, 2])
        self.assertEqual(result["states"][0]["version"], 2)

    def test_retries_use_exponential_backoff_and_stop(self):
        result = run({"events": [event(failures=99)], "ticks": [0, .5, 1, 2, 3, 10], "max_attempts": 3})
        self.assertEqual([r["time_seconds"] for r in result["trace"]], [0, 1, 3])
        self.assertEqual(result["records"][0]["status"], "dead_letter")
        self.assertEqual(result["records"][0]["attempts"], 3)

    def test_missing_predecessor_dead_letters_after_order_wait_budget(self):
        result = run({"events": [event(version=3)], "ticks": [0, 1, 2, 3], "max_order_waits": 3})
        self.assertEqual(result["records"][0]["status"], "dead_letter")
        self.assertEqual(result["records"][0]["attempts"], 0)
        self.assertEqual(result["states"], [])

    def test_alternate_key_cannot_overwrite_applied_version(self):
        result = run({"events": [event("a"), event("b")]})
        self.assertEqual(result["metrics"]["delivered"], 1)
        self.assertEqual({r["status"] for r in result["records"]}, {"delivered", "superseded"})

    def test_dedup_and_retry_state_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "relay.sqlite3")
            first = RelayStore(path)
            first.ingest(event(failures=1))
            first.process(0)
            first.close()
            second = RelayStore(path)
            try:
                self.assertEqual(second.ingest(event())["status"], "duplicate")
                self.assertEqual(second.process(.5), [])
                self.assertEqual(second.process(1)[0]["status"], "delivered")
                self.assertEqual(second.records()[0]["attempts"], 2)
            finally:
                second.close()

    def test_pending_horizon_is_explicit(self):
        result = run({"events": [event(failures=2)], "ticks": [0]})
        self.assertEqual(result["metrics"]["pending"], 1)
        self.assertTrue(any("horizon" in text for text in result["warnings"]))

    def test_sink_storage_failure_rolls_back_delivery_and_attempt(self):
        store = RelayStore()
        try:
            store.ingest(event())
            store.db.execute("CREATE TRIGGER fail_sink BEFORE INSERT ON aggregates BEGIN SELECT RAISE(ABORT, 'sink failure'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                store.process(0)
            self.assertEqual(store.states(), [])
            self.assertEqual(store.records()[0]["status"], "pending")
            self.assertEqual(store.records()[0]["attempts"], 0)
            store.db.execute("DROP TRIGGER fail_sink")
            self.assertEqual(store.process(0)[0]["status"], "delivered")
        finally:
            store.close()

    def test_invalid_inputs_fail_without_silent_coercion(self):
        cases = [{"events": [event()], "ticks": [1, 0]}, {"events": [event()], "ticks": [float("nan")]},
                 {"events": [event(version=True)]}, {"events": [event()], "max_attempts": 0},
                 {"events": [event()], "base_delay_seconds": 0}, {"events": "wrong"}]
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                run(payload)

    def test_nan_payload_rejected(self):
        item = event()
        item["body"] = {"amount": float("nan")}
        with self.assertRaises(ValueError):
            run({"events": [item]})


if __name__ == "__main__":
    unittest.main()
