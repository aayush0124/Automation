# FIELDKIT / FDE Lab

**Ten customer problems. Executable workflows. Evidence you can inspect.**

A forward deployed engineering portfolio by **Aayush Paliwal**. Built around the work employers describe: discovery, messy integrations, application delivery, evaluations, operational decisions, and customer handoff.

These are **working reference implementations using synthetic data**, not claimed client deployments. Every result is calculated from the submitted input. The core has no third-party Python dependencies, paid API requirement, network integration, or downloaded model. A tools-only MCP server lets an external agent call the same engines.

## Run in two commands

Requires Python **3.11+**. From the `fieldkit-fde` directory:

```bash
python -m unittest discover -s tests
python -m fieldkit serve
```

Open **http://127.0.0.1:8787**. Choose a project, change its JSON fixture, run it, and inspect decisions and evidence. No package installation is needed.

```bash
python -m fieldkit list
python -m fieldkit run dockyard
python -m fieldkit sample proofdesk
python -m fieldkit run proofdesk --input your-scenario.json
python -m fieldkit.mcp
python -m fieldkit export
```

The last command executes all ten samples and refreshes `web/catalog.json` and `web/examples/`. On a static host, the interface labels them **recorded fixture replay** and disables input editing. The live interface runs the Python engines. Opening `index.html` directly as a file is not supported; use an HTTP server.

## Ten projects, three tracks

Order is our portfolio-priority assessment, not an employer ranking. Read the [research and selection rationale](docs/RESEARCH.md).

| Rank | Project | What a reviewer can actually test | Track |
|---|---|---|---|
| 1 | **[Dockyard](docs/projects/dockyard.md)** · flagship | Normalize CRM CSV, preserve cell lineage, deduplicate, quarantine conflicting identities | Enterprise AI |
| 2 | **[ProofDesk](docs/projects/proofdesk.md)** · flagship | Retrieve cited evidence with tenant/role/version/freshness rules and abstention | Enterprise AI |
| 3 | **[EvalForge](docs/projects/evalforge.md)** · flagship | Compare paired agent outputs, enforce critical cases, cost/latency budgets and release gates | Deployment reliability |
| 4 | [LedgerGuard](docs/projects/ledgerguard.md) | Match invoices, purchase orders and receipts using exact money and atomic quantity reservations | Operational systems |
| 5 | [Relay](docs/projects/relay.md) | Replay webhook failures through a transactional SQLite inbox/outbox with deduplication and DLQ | Deployment reliability |
| 6 | [Switchboard](docs/projects/switchboard.md) | Trace incident blast radius and rank possible causes with inspectable evidence | Operational systems |
| 7 | [RouteCraft](docs/projects/routecraft.md) | Assign delivery routes under capacity, completion windows and return-to-depot limits | Operational systems |
| 8 | [ConsentLine](docs/projects/consentline.md) | Redact or pseudonymize detected identifiers and apply purpose/consent rules before egress | Enterprise AI |
| 9 | [ShiftForge](docs/projects/shiftforge.md) | Schedule dependent jobs around machine skills, maintenance and deadlines | Operational systems |
| 10 | [LaunchGate](docs/projects/launchgate.md) | Recommend approve/hold/rollback from supplied canary counters, latency samples and SLO policy | Deployment reliability |

Each linked case study includes a customer problem, inputs, architecture, a 90-second demonstration, a failure injection, acceptance checks, limitations and a production backlog. See the [interview demo guide](docs/DEMO_GUIDE.md) for three presentation options.

## Engineering evidence

- Independent domain tests cover invalid input, permission revocation, currency mismatches, retry persistence, ordering, scheduling constraints and release blockers.
- HTTP handler tests execute every workflow and probe Host/Origin checks, JSON validation, path traversal and audit privacy. Socket tests run where loopback networking is permitted; restricted environments report skips explicitly.
- SQLite audit keeps run ID, project ID, input hash, elapsed milliseconds and timestamp, **not request bodies or result contents**. It retains the most recent 1,000 successful runs locally.
- The MCP interface exposes an explicit ten-tool allowlist. Tools calculate results; they do not send payments, change production, fetch URLs or execute proposed commands.
- Static examples are generated from the actual engines and are checked for reproducibility.

See [verification evidence](evidence/verification.json), [architecture](docs/ARCHITECTURE.md), [security boundaries](SECURITY.md), and [MCP setup](docs/MCP.md). Exact pass/skip counts and verification limits are in the evidence file.

## Honest boundaries

ProofDesk is lexical evidence retrieval, not semantic RAG or generated answering. EvalForge scores supplied outputs, not live model quality. ConsentLine uses incomplete regex detectors and is not a compliance certification. Planning and incident engines are transparent heuristics. Relay models external delivery failures; it does not claim exactly-once network delivery. LaunchGate recommends a decision but never deploys.

The web server is intentionally loopback-only; `FIELDKIT_ENV=production` refuses startup. User and document permissions are sample inputs, not authenticated identities. Before a real rollout, add verified authentication, trusted source connectors, tenant enforcement, secret management, a production server, monitoring and customer acceptance testing. No customer ROI, enterprise readiness or actual adoption is claimed.

## Repository layout

```text
fieldkit/projects/   ten independent engines and synthetic fixtures
fieldkit/           CLI, bounded registry, local API, audit, MCP, static exporter
web/                interactive interface and generated sample evidence
tests/              domain, integration, protocol and regression checks
docs/projects/      customer briefs and demonstration runbooks
evidence/           measured verification record
```

Published as an isolated `portfolio/fieldkit-fde` branch in `aayush0124/Automation`, under `fieldkit-fde/`. The original project's files are preserved. This directory can be moved into its own repository without changing imports or commands. A root-level workflow on the portfolio branch runs the tests; the portable workflow template is in `scripts/fieldkit-ci.yml`.

MIT licensed. New portfolio implementation created with AI-assisted engineering; test results and stated limits are inspectable.
