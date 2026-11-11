"""Independent end-to-end checks against real loopback HTTP and SQLite audit storage."""
import copy
import http.client
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fieldkit.audit import AuditStore
from fieldkit.registry import MAX_BYTES, PROJECT_IDS, execute, get_project, parse_json
from fieldkit.server import FieldkitHandler, create_server


class RuntimeHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.audit_path = Path(cls.temp.name) / "audit.sqlite3"
        with patch.dict(os.environ, {"FIELDKIT_ENV": "local"}):
            cls.server = create_server(0, cls.audit_path)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        probe = http.client.HTTPConnection("127.0.0.1", cls.server.server_port, timeout=5)
        try:
            probe.request("GET", "/api/health")
            probe.getresponse().read()
        except PermissionError as exc:
            cls.server.shutdown()
            cls.server.server_close()
            cls.thread.join(timeout=5)
            cls.temp.cleanup()
            raise unittest.SkipTest(f"Environment disallows loopback socket connections: {exc}") from exc
        finally:
            probe.close()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temp.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def post(self, project, payload):
        return self.request(f"/api/run/{project}", "POST", json.dumps(payload), {"Content-Type": "application/json"})

    def test_all_ten_sample_workflows_execute_through_http(self):
        status, _, body = self.request("/api/projects")
        self.assertEqual(status, 200)
        catalog = json.loads(body)["projects"]
        self.assertEqual({p["id"] for p in catalog}, set(PROJECT_IDS))
        self.assertEqual(len(catalog), 10)
        for project in catalog:
            with self.subTest(project=project["id"]):
                status, _, detail = self.request("/api/projects/" + project["id"])
                self.assertEqual(status, 200)
                sample = json.loads(detail)["sample"]
                status, headers, body = self.post(project["id"], sample)
                self.assertEqual(status, 200, body.decode())
                result = json.loads(body)
                self.assertEqual(result["project_id"], project["id"])
                self.assertTrue(result["run_id"])
                self.assertEqual(len(result["input_sha256"]), 64)
                self.assertGreaterEqual(result["elapsed_ms"], 0)
                self.assertIsInstance(result["result"]["summary"], str)
                self.assertIsInstance(result["result"]["records"], list)
                self.assertIsInstance(result["result"]["metrics"], dict)
                self.assertIsInstance(result["result"]["warnings"], list)
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_health_and_security_headers(self):
        status, headers, body = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["mode"], "local-demo")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_foreign_host_is_rejected(self):
        status, _, _ = self.request("/api/health", headers={"Host": "attacker.invalid"})
        self.assertEqual(status, 403)

    def test_foreign_origin_rejected_even_with_valid_loopback_host(self):
        status, _, _ = self.request("/api/health", headers={"Origin": "https://attacker.invalid"})
        self.assertEqual(status, 403)

    def test_local_origin_permitted(self):
        status, _, _ = self.request("/api/health", headers={"Origin": f"http://127.0.0.1:{self.server.server_port}"})
        self.assertEqual(status, 200)

    def test_json_content_type_required(self):
        status, _, _ = self.request("/api/run/relay", "POST", "{}", {"Content-Type": "text/plain"})
        self.assertEqual(status, 415)

    def test_missing_or_oversized_body_rejected_before_parsing(self):
        for body, headers in [(None, {"Content-Type": "application/json"}),
                              (b"", {"Content-Type": "application/json", "Content-Length": str(MAX_BYTES + 1)})]:
            with self.subTest(headers=headers):
                status, _, _ = self.request("/api/run/relay", "POST", body, headers)
                self.assertEqual(status, 413)

    def test_chunked_request_rejected(self):
        status, _, _ = self.request("/api/run/relay", "POST", "{}", {"Content-Type": "application/json", "Transfer-Encoding": "chunked"})
        self.assertEqual(status, 400)

    def test_malformed_duplicate_nonfinite_and_nonobject_json_rejected(self):
        for body in ('{"events":', '{"events":[],"events":[]}', '{"events":[],"x":NaN}', '[]', b"\xff"):
            with self.subTest(body=body):
                status, _, _ = self.request("/api/run/relay", "POST", body, {"Content-Type": "application/json"})
                self.assertEqual(status, 400)

    def test_unknown_project_cannot_import_arbitrary_module(self):
        status, _, _ = self.post("os", {})
        self.assertEqual(status, 400)
        status, _, _ = self.request("/api/projects/os")
        self.assertEqual(status, 404)

    def test_traversal_and_internal_files_are_not_served(self):
        for path in ("/../fieldkit/server.py", "/%2e%2e/fieldkit/server.py", "/..%5cfieldkit%5cserver.py",
                     "/.git/config", "/fieldkit/server.py", "/%2e%2e/.local/audit.sqlite3"):
            with self.subTest(path=path):
                status, _, _ = self.request(path)
                self.assertEqual(status, 404)

    def test_invalid_path_returns_not_found_without_aborting_connection(self):
        status, _, _ = self.request("/%00")
        self.assertEqual(status, 404)

    def test_audit_contains_only_metadata_and_survives_reopening(self):
        sentinel = "PRIVATE_CUSTOMER_PAYLOAD_72da9b"
        payload = {"events": [{"tenant": "demo", "key": "privacy", "aggregate": "record", "version": 1,
                               "body": {"private": sentinel}}]}
        status, _, body = self.post("relay", payload)
        self.assertEqual(status, 200)
        run_id = json.loads(body)["run_id"]
        reopened = AuditStore(self.audit_path)
        rows = reopened.recent()
        record = next(row for row in rows if row["run_id"] == run_id)
        self.assertEqual(set(record), {"run_id", "project_id", "input_sha256", "elapsed_ms", "created_at"})
        connection = sqlite3.connect(self.audit_path)
        try:
            dump = "\n".join(connection.iterdump())
        finally:
            connection.close()
        self.assertNotIn(sentinel, dump)
        self.assertNotIn("private", dump)
        status, _, body = self.request("/api/runs")
        self.assertEqual(status, 200)
        self.assertNotIn(sentinel, body.decode())
        self.assertTrue(any(row["run_id"] == run_id for row in json.loads(body)["runs"]))


class RuntimeHandlerTests(RuntimeHTTPTests):
    """Same HTTP contract checks through real parsing/handlers, without OS transport.

    This complements, and explicitly does not replace, the live HTTP server tests.
    It allows handler verification when the execution sandbox blocks loopback sockets.
    """

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.audit_path = Path(cls.temp.name) / "audit.sqlite3"
        cls.server = SimpleNamespace(server_port=8787, audit=AuditStore(cls.audit_path))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        values = {"Host": "127.0.0.1:8787", **(headers or {})}
        data = body.encode("utf-8") if isinstance(body, str) else body or b""
        if method == "POST" and "Content-Length" not in values:
            values["Content-Length"] = str(len(data))
        head = f"{method} {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in values.items()) + "\r\n"

        class MemoryConnection:
            def __init__(self, request):
                self.request = io.BytesIO(request)
                self.response = bytearray()

            def makefile(self, *_args, **_kwargs):
                return self.request

            def settimeout(self, _timeout):
                pass

            def sendall(self, value):
                self.response.extend(value)

        connection = MemoryConnection(head.encode("ascii") + data)
        FieldkitHandler(connection, ("127.0.0.1", 12345), self.server)
        raw_headers, response_body = bytes(connection.response).split(b"\r\n\r\n", 1)
        lines = raw_headers.decode("latin-1").split("\r\n")
        response_headers = dict(line.split(": ", 1) for line in lines[1:])
        return int(lines[0].split(" ")[1]), response_headers, response_body


class RuntimeBoundaryTests(unittest.TestCase):
    def test_production_mode_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"FIELDKIT_ENV": "production"}):
            with self.assertRaisesRegex(ValueError, "Production serving is disabled"):
                create_server(0, Path(tmp) / "audit.sqlite3")

    def test_payload_limits_and_duplicate_keys_rejected(self):
        values = ['{"a":1,"a":2}', '{"a":Infinity}', '{"a":' + "[" * 30 + "0" + "]" * 30 + "}",
                  json.dumps({"items": list(range(501))}), json.dumps({"s": "x" * MAX_BYTES})]
        for value in values:
            with self.subTest(length=len(value)), self.assertRaises(ValueError):
                parse_json(value)

    def test_hash_reproducible_and_caller_input_unchanged(self):
        payload = copy.deepcopy(get_project("relay").SAMPLE)
        before = copy.deepcopy(payload)
        first, second = execute("relay", payload), execute("relay", payload)
        self.assertEqual(payload, before)
        self.assertEqual(first["input_sha256"], second["input_sha256"])
        self.assertEqual(first["result"], second["result"])
        self.assertNotEqual(first["run_id"], second["run_id"])

    def test_audit_survives_actual_server_restart(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"FIELDKIT_ENV": "local"}):
            path = Path(tmp) / "audit.sqlite3"
            first = create_server(0, path)
            run = execute("relay", {"events": []})
            first.audit.append(run)
            first.server_close()
            second = create_server(0, path)
            thread = threading.Thread(target=second.serve_forever, daemon=True)
            thread.start()
            connection = http.client.HTTPConnection("127.0.0.1", second.server_port, timeout=5)
            try:
                try:
                    connection.request("GET", "/api/runs")
                except PermissionError as exc:
                    self.skipTest(f"Environment disallows loopback socket connections: {exc}")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read())["runs"][0]["run_id"], run["run_id"])
            finally:
                connection.close()
                second.shutdown()
                second.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
