# What makes a strong FDE portfolio?

Research checked **11 November 2026**. FDE means **Forward Deployed Engineer** here. Job postings are volatile; these links support the hiring signals, not a promise of current eligibility or interview success.

## First-party evidence

| Source | Verified emphasis | What we built in response |
|---|---|---|
| [OpenAI FDE role](https://openai.com/careers/forward-deployed-engineer-uae-abu-dhabi-uae/) | Full-stack delivery, customer immersion, ambiguous scoping and reusable patterns | One runnable lab, customer briefs, narrow measurable workflows |
| [OpenAI FDE practice](https://openai.com/business/forward-deployed-engineering/) | Discovery, representative and difficult-case validation, permissions, monitoring and handoff | Failure injections, audit metadata, acceptance checks and deployment gaps |
| [Anthropic FDE](https://job-boards.greenhouse.io/anthropic/jobs/5391016008) | Production LLM applications, agents/evaluations, MCP tools and enterprise integration | Evidence retrieval, paired evaluation, bounded MCP tool interface |
| [Databricks FDE](https://www.databricks.com/company/careers/professional-services-operations/forward-deployed-engineer-8921476002) | Architecture, secure full-stack delivery, data ingestion, integrations and reusable assets | Data reconciliation, operational engines, shared API and inspectable outputs |

The specific Anthropic posting is for Munich and includes language/seniority requirements. These are examples of role expectations, not a shortlist of personally matched openings. A portfolio demonstrates engineering ability; it does not replace required experience.

## Selection method

We considered customer specificity (25 points), executable scope (20), evaluation/failure handling (20), integration difficulty (15), demo distinctiveness (10), and deployment/handoff (10). This is our qualitative selection rubric, not an externally validated score. We did not assign pseudo-precise numerical scores to untested job-market outcomes.

| Priority | Project | Why it earns a place | Highest-value next validation |
|---|---|---|---|
| 1 | Dockyard | Messy integration plus explainable data quality is common to customer deployments | Run an approved, anonymized real CRM migration and compare reconciliation with operator review |
| 2 | ProofDesk | Demonstrates a meaningful access boundary and honest abstention | Trusted identity/doc sync, adversarial retrieval evaluation, then a model answer adapter |
| 3 | EvalForge | Converts an impressive demo into an explicit release decision | Capture real baseline/candidate model runs and evaluate on held-out customer tasks |
| 4 | LedgerGuard | High-value reconciliation with concrete edge cases | Shadow a customer's AP workflow without payment execution |
| 5 | Relay | Integration reliability is visible, persistent and testable | Signed webhooks and a controlled external sink with crash-injection testing |
| 6 | Switchboard | Turns topology and incident evidence into an explainable investigation | Replay incident histories and compare ranking with postmortems |
| 7 | RouteCraft | Makes operational constraints and optimization tradeoffs visible | Add a verified road-time matrix and compare against a solver |
| 8 | ConsentLine | Demonstrates minimization before data crosses a boundary | Evaluate detector recall and consent lifecycle against approved enterprise examples |
| 9 | ShiftForge | Schedules constrained resources with dependencies and exceptions | Apply to factory jobs or a media/render queue with measured processing times |
| 10 | LaunchGate | Connects technical telemetry to staged rollout judgment | Trusted telemetry integration, shadow recommendations and approved rollback procedures |

## Three portfolio options

1. **AI FDE applications — recommended:** lead with ProofDesk, EvalForge and the MCP interface; use Dockyard to explain the integration groundwork.
2. **Data/platform FDE applications:** lead with Dockyard, Relay and LedgerGuard; show lineage, transactions and migration failure handling.
3. **Operations FDE applications:** lead with RouteCraft, ShiftForge and Switchboard; show constrained decisions and explain tradeoffs to a customer stakeholder.

All ten are implemented. Three get flagship positioning so a reviewer has a focused entry point. This is a breadth-first portfolio release; the next credible advancement is a real, consented pilot with measured acceptance, not an invented customer-success metric.

## Commercial hypotheses

The same work can support paid discovery and implementation engagements: migration readiness, support knowledge integration, agent-release evaluation, AP reconciliation, webhook reliability or operational scheduling. Validate willingness to pay with an actual customer before quoting ROI. Use a small paid pilot with a predefined acceptance test, then offer maintenance only after observing production needs. No revenue or savings have been measured in this portfolio.

## Technical references

- [Python HTTP server documentation](https://docs.python.org/3/library/http.server.html): the standard server is a development component, not a production serving recommendation.
- [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) and [lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle): newline JSON-RPC and capability/version negotiation.
- [GitHub Python CI guidance](https://docs.github.com/en/actions/tutorials/build-and-test-code/python): workflow structure and Python test execution.
