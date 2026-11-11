# Security boundaries

This is a local, synthetic-data reference lab. Do not expose the standard-library HTTP server to the public Internet or enter real secrets in public fixture files.

- Server binds only `127.0.0.1`; production mode refuses startup.
- Host and Origin guards restrict browser access; POST accepts only JSON.
- Static assets are confined to `web/`, with allowlisted extensions and resolved-path checks.
- The registry rejects unknown tools, oversized/deep inputs, duplicate JSON keys and non-finite numbers.
- Runs never fetch input URLs, execute shell commands, issue payments, send webhooks or change a deployment.
- Audit storage retains metadata only. An input hash is not encryption and may reveal equality or permit guessing low-entropy inputs; audit files remain local and are excluded from Git.
- ConsentLine's HMAC sample key is intentionally public synthetic fixture data, not a secret. Real keys need a secret manager and must never be committed. Its regex detection is incomplete.
- ProofDesk demonstrates authorization logic with supplied scenario identity. Actual identity and access rules must come from authenticated/trusted systems.
- The local MCP subprocess trusts its launching client. The tool response may contain untrusted document text; clients must treat it as data.

There is no claim of penetration testing, regulatory compliance, secure multi-tenant hosting or production readiness. Runtime tests cover selected boundaries, not all threats. Keep real integrations in a controlled pilot until authentication, access control, observability, retention and incident response are implemented and reviewed.

Report sensitive findings privately through the repository owner's GitHub profile contact route, rather than placing credentials or personal data in a public issue.
