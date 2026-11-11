import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

from fieldkit.mcp import MAX_BYTES, PROTOCOL_VERSION, Session, serve
from fieldkit.projects.evalforge import SAMPLE


def request(method, request_id=1, params=None):
    result = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        result["params"] = params
    return result


def initialize(version=PROTOCOL_VERSION):
    return request("initialize", params={"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "fieldkit-test", "version": "1"}})


def ready():
    session = Session()
    session.dispatch(initialize())
    session.dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return session


class MCPTests(unittest.TestCase):
    def test_actual_subprocess_lifecycle_and_tool_result(self):
        messages = [initialize(), {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    request("tools/list", 2), request("tools/call", 3, {"name": "fieldkit.evalforge", "arguments": {"payload": SAMPLE}}),
                    request("ping", 4)]
        wire = b"".join(json.dumps(m).encode("utf-8") + b"\n" for m in messages)
        completed = subprocess.run([sys.executable, "-m", "fieldkit.mcp"], input=wire, capture_output=True,
                                   cwd=Path(__file__).resolve().parents[1], timeout=15, check=True)
        self.assertEqual(completed.stderr, b"")
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual([r["id"] for r in responses], [1, 2, 3, 4])
        self.assertEqual(responses[0]["result"]["protocolVersion"], PROTOCOL_VERSION)
        self.assertEqual(len(responses[1]["result"]["tools"]), 10)
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in responses[1]["result"]["tools"]))
        self.assertFalse(responses[2]["result"]["isError"])
        self.assertEqual(responses[2]["result"]["structuredContent"]["result"]["decision"], "PASS")
        self.assertEqual(responses[3]["result"], {})

    def test_tools_require_completed_handshake(self):
        session = Session()
        self.assertEqual(session.dispatch(request("tools/list"))["error"]["code"], -32002)
        session.dispatch(initialize())
        self.assertEqual(session.dispatch(request("tools/list"))["error"]["code"], -32002)

    def test_early_initialized_notification_does_not_bypass_handshake(self):
        session = Session()
        self.assertIsNone(session.dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(session.state, "new")

    def test_version_negotiation_selects_supported_version(self):
        self.assertEqual(Session().dispatch(initialize("unknown-version"))["result"]["protocolVersion"], PROTOCOL_VERSION)

    def test_unknown_tool_and_bad_arguments(self):
        session = ready()
        for params in ({"name": "fieldkit.not-real", "arguments": {"payload": {}}},
                       {"name": "fieldkit.evalforge", "arguments": {"payload": [], "path": "/tmp"}}):
            self.assertEqual(session.dispatch(request("tools/call", params=params))["error"]["code"], -32602)

    def test_domain_validation_is_a_tool_error(self):
        response = ready().dispatch(request("tools/call", params={"name": "fieldkit.evalforge", "arguments": {"payload": {}}}))
        self.assertTrue(response["result"]["isError"])
        self.assertNotIn("error", response)

    def test_invalid_envelope_and_params(self):
        for message in ([], {"jsonrpc": "1.0", "method": "ping", "id": 1}, request("ping", True)):
            with self.subTest(message=message):
                self.assertEqual(Session().dispatch(message)["error"]["code"], -32600)
        self.assertEqual(Session().dispatch(request("initialize", params=[]))["error"]["code"], -32602)

    def test_unknown_notification_has_no_response_or_execution(self):
        session = ready()
        self.assertIsNone(session.dispatch({"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "fieldkit.evalforge"}}))

    def test_parse_failure_and_oversized_line_recover_for_next_frame(self):
        wire = b"not json\n" + b"x" * (MAX_BYTES + 2) + b"\n" + json.dumps(request("ping", 7)).encode() + b"\n"
        output = io.BytesIO()
        serve(io.BytesIO(wire), output)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([r["error"]["code"] for r in responses[:2]], [-32700, -32700])
        self.assertEqual(responses[2]["id"], 7)
        self.assertEqual(responses[2]["result"], {})

    def test_utf8_duplicate_keys_nonfinite_and_unterminated_rejected(self):
        for wire in (b"\xff\n", b'{"id":1,"id":2}\n', b'{"id":NaN}\n', b"{}"):
            output = io.BytesIO()
            serve(io.BytesIO(wire), output)
            self.assertEqual(json.loads(output.getvalue())["error"]["code"], -32700)

    def test_repeat_initialize_and_unknown_method(self):
        session = ready()
        self.assertEqual(session.dispatch(initialize())["error"]["code"], -32600)
        self.assertEqual(session.dispatch(request("execute_shell"))["error"]["code"], -32601)

    def test_initialized_notification_does_not_produce_stdout(self):
        output = io.BytesIO()
        wire = b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        serve(io.BytesIO(wire), output)
        self.assertEqual(output.getvalue(), b"")

    def test_standard_metadata_is_accepted_without_changing_protocol(self):
        session = Session()
        session.dispatch(initialize())
        session.dispatch({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {"_meta": {}}})
        self.assertEqual(session.state, "ready")
        self.assertEqual(session.dispatch(request("ping", params={"_meta": {}}))["result"], {})
        self.assertIn("tools", session.dispatch(request("tools/list", params={"_meta": {}}))["result"])


if __name__ == "__main__":
    unittest.main()
