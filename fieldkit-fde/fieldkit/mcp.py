"""Bounded, tools-only MCP stdio bridge for local FieldKit computations.

Protocol messages alone go to stdout. No file paths, shell commands or network
requests are accepted. This is intentionally a small protocol implementation,
not a claim of complete MCP conformance or a production MCP gateway.
"""

from __future__ import annotations

import json
import math
import sys
from typing import Any, BinaryIO

from fieldkit.registry import MAX_BYTES, execute, get_project, list_projects, validate_json

PROTOCOL_VERSION = "2025-11-25"
MAX_OUTPUT_BYTES = 4 * MAX_BYTES


class RPCError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _result(request_id: Any, value: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) or (not isinstance(value, bool) and isinstance(value, (int, float))
                                      and (not isinstance(value, float) or math.isfinite(value)))


def _only_meta(params: dict) -> bool:
    return not (set(params) - {"_meta"}) and ("_meta" not in params or isinstance(params["_meta"], dict))


def _decode(line: bytes) -> Any:
    def reject_constant(_):
        raise ValueError("Non-finite JSON is not accepted")

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate object keys are not accepted")
            result[key] = value
        return result

    return json.loads(line.decode("utf-8"), parse_constant=reject_constant, object_pairs_hook=unique_keys)


class Session:
    """One subprocess = one negotiated session. Tool execution is synchronous."""

    def __init__(self):
        self.state = "new"

    def dispatch(self, message: Any) -> dict | None:
        request_id = message.get("id") if isinstance(message, dict) else None
        if not _valid_id(request_id):
            request_id = None
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(request_id, -32600, "Expected one JSON-RPC 2.0 object; batches are not supported")
        # No server requests are sent, so incoming responses have no matching work.
        if "method" not in message and ("result" in message or "error" in message):
            return None
        method = message.get("method")
        if not isinstance(method, str) or not method:
            return _error(request_id, -32600, "method must be a non-empty string")
        notification = "id" not in message
        if not notification and not _valid_id(message["id"]):
            return _error(None, -32600, "Request id must be a string or finite number")
        if "result" in message or "error" in message:
            return None if notification else _error(request_id, -32600, "Requests cannot also contain a response")
        try:
            validate_json(message)
        except (ValueError, RecursionError):
            return None if notification else _error(request_id, -32600, "Message exceeds JSON shape limits")
        params = message.get("params", {})
        if not isinstance(params, dict):
            return None if notification else _error(request_id, -32602, "params must be an object")
        if notification:
            # Notifications never receive a response, even when unsupported.
            if method == "notifications/initialized" and self.state == "negotiated" and _only_meta(params):
                self.state = "ready"
            return None
        try:
            value = self._request(method, params)
            response = _result(request_id, value)
            if len(json.dumps(response, ensure_ascii=True, allow_nan=False).encode("utf-8")) > MAX_OUTPUT_BYTES:
                return _result(request_id, {"content": [{"type": "text", "text": "Result exceeds the 4 MiB response budget; narrow the input."}], "isError": True})
            return response
        except RPCError as exc:
            return _error(request_id, exc.code, str(exc))
        except Exception:
            # Do not expose a stack trace, environment details, or input secrets.
            return _error(request_id, -32603, "Internal calculation error")

    def _request(self, method: str, params: dict) -> dict:
        if method == "initialize":
            if self.state != "new":
                raise RPCError(-32600, "Session is already initialized")
            info = params.get("clientInfo")
            if (not isinstance(params.get("protocolVersion"), str) or not params["protocolVersion"]
                    or not isinstance(params.get("capabilities"), dict)
                    or not isinstance(info, dict)
                    or any(not isinstance(info.get(k), str) or not info[k] for k in ("name", "version"))):
                raise RPCError(-32602, "initialize requires protocolVersion, capabilities and clientInfo.name/version")
            self.state = "negotiated"
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "fieldkit-fde", "version": "0.1.0", "title": "FieldKit local workflow tools"},
                "instructions": "Local synthetic workflow calculations only. Pass a project input object inside arguments.payload. Results are evidence for review, not external execution or production authorization.",
            }
        if method == "ping":
            if not _only_meta(params):
                raise RPCError(-32602, "ping takes no parameters")
            return {}
        if self.state != "ready":
            raise RPCError(-32002, "Complete initialize and notifications/initialized before using tools")
        if method == "tools/list":
            if not _only_meta(params):
                raise RPCError(-32602, "This bounded tool list has one page and accepts no cursor")
            entries = []
            for spec in list_projects():
                entries.append({
                    "name": "fieldkit." + spec["id"], "title": spec["name"],
                    "description": spec["description"] + " Local, supplied data only; see the payload example for this project's contract.",
                    "inputSchema": {
                        "type": "object", "properties": {
                            "payload": {"type": "object", "description": "Project-specific JSON input; validated by the domain engine.",
                                        "examples": [get_project(spec["id"]).SAMPLE]},
                        }, "required": ["payload"], "additionalProperties": False,
                    },
                    "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
                })
            return {"tools": entries}
        if method == "tools/call":
            name, arguments = params.get("name"), params.get("arguments")
            if not isinstance(name, str) or not name.startswith("fieldkit."):
                raise RPCError(-32602, "Unknown tool")
            project_id = name[len("fieldkit."):]
            try:
                get_project(project_id)
            except ValueError as exc:
                raise RPCError(-32602, "Unknown tool") from exc
            if not isinstance(arguments, dict) or set(arguments) != {"payload"} or not isinstance(arguments["payload"], dict):
                raise RPCError(-32602, "Tool arguments must contain exactly one object named payload")
            if set(params) - {"name", "arguments", "_meta"}:
                raise RPCError(-32602, "Unsupported tools/call parameter")
            try:
                envelope = execute(project_id, arguments["payload"])
            except ValueError as exc:
                return {"content": [{"type": "text", "text": "Input rejected: " + str(exc)}], "isError": True}
            return {"content": [{"type": "text", "text": json.dumps(envelope, ensure_ascii=True, allow_nan=False)}],
                    "structuredContent": envelope, "isError": False}
        raise RPCError(-32601, "Method not found")


def serve(input_stream: BinaryIO, output_stream: BinaryIO) -> None:
    session = Session()
    while True:
        line = input_stream.readline(MAX_BYTES + 1)
        if not line:
            return
        if len(line) > MAX_BYTES:
            # Drain the rejected frame in bounded chunks, retaining no payload.
            while line and not line.endswith(b"\n"):
                line = input_stream.readline(MAX_BYTES + 1)
            response = _error(None, -32700, "Message exceeds 1 MiB line budget")
        elif not line.endswith(b"\n"):
            response = _error(None, -32700, "Messages must end with a newline")
        else:
            try:
                message = _decode(line)
            except (UnicodeError, ValueError, RecursionError):
                response = _error(None, -32700, "Invalid UTF-8 JSON message")
            else:
                response = session.dispatch(message)
        if response is not None:
            try:
                output_stream.write(json.dumps(response, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n")
                output_stream.flush()
            except BrokenPipeError:
                return


def main() -> None:
    serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    main()
