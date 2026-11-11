# Local agent tool boundary

FieldKit includes a bounded **tools-only MCP stdio implementation** targeting protocol version `2025-11-25`. It makes the ten project engines callable through a real JSON-RPC subprocess boundary. It has subprocess integration tests; it has **not** been verified with an external MCP client or certified for full specification compliance.

## Start

From the repository root, with Python 3.11 or newer:

```bash
python -m fieldkit.mcp
```

An MCP host should launch that command with the repository root as its working directory. The process reads UTF-8, newline-delimited JSON-RPC from stdin and writes only protocol messages to stdout. Closing stdin ends the process. No network listener is created.

## Handshake and tool invocation

Send an `initialize` request with protocol version, capabilities and client name/version. The server returns its supported version, server metadata, and `tools` capability. If the host does not support the returned version, disconnect. Then send `notifications/initialized`; notifications receive no response.

After that, `tools/list` returns ten tools named `fieldkit.<project_id>`. Each input schema contains a complete synthetic payload example. For example, `fieldkit.evalforge` receives:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "fieldkit.evalforge",
    "arguments": {
      "payload": {
        "cases": [{"id": "one", "expected": "OK"}],
        "baseline": [{"case_id": "one", "output": "OK", "latency_ms": 10, "cost_usd": 0}],
        "candidate": [{"case_id": "one", "output": "OK", "latency_ms": 9, "cost_usd": 0}],
        "thresholds": {"min_cases": 1}
      }
    }
  }
}
```

Results include both a text JSON representation and `structuredContent` containing the registry run envelope, input hash, elapsed time and domain evidence. An accepted experiment is not deployment approval. Invalid project inputs return `isError: true`; protocol errors use JSON-RPC error responses.

## Implemented boundary

| Capability | Behavior |
|---|---|
| Lifecycle | Initialize/version selection, initialized notification, ping, EOF shutdown |
| Tools | Static list, ten allowlisted computation tools, object arguments |
| Input budgets | 1 MiB per newline frame; registry nesting, object and array limits |
| Output budget | 4 MiB per response; oversized calculations return an error result |
| Error handling | Parse/envelope/parameter/method errors; domain errors distinct from protocol errors |
| Side effects | No external actions, supplied file paths, shell execution or outbound requests |
| Annotations | Read-only, non-destructive, closed-world calculations; hints are not authorization |

The sample key in ConsentLine is explicitly public synthetic test material. Never replace it with a production secret in a committed fixture. Client-supplied identities and consent are test inputs, not authenticated claims.

## Verification and limits

```bash
python -m unittest discover -s tests -p test_mcp.py -v
```

Tests launch the actual subprocess and complete initialize → initialized → tools/list → tools/call → ping → stdin close. Additional checks cover pre-handshake calls, unknown tools, malformed arguments, domain validation, invalid UTF-8/JSON, duplicate keys, non-finite numbers, oversize-frame recovery and notification silence.

This implementation is sequential. It does not implement HTTP, authentication, resources, prompts, sampling, elicitation, tasks, progress, cancellation, dynamic tool updates or pagination. Long synchronous calculations cannot be cancelled in-process; hosts should enforce subprocess timeouts. The bridge trusts its local host and never treats annotations as a security mechanism. Before a real deployment, use a maintained MCP SDK, validate with target clients, add authenticated identity at real connectors, and review resource isolation and telemetry handling.

## Primary protocol references

Reviewed against official specification pages on 11 November 2026:

- [Lifecycle and version negotiation](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)
- [Stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [Tools, schema and error handling](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)

These references establish the protocol behavior; the repository tests establish only the implementation paths exercised here.
