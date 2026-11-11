# EvalForge

**Customer problem:** a support team wants to replace its policy agent. The new version looks better in a demo, but an improvement in average quality can hide one unauthorized disclosure, missing citation, or unacceptable cost increase.

EvalForge is a deterministic paired acceptance bench. It scores supplied baseline and candidate outputs against labeled cases, explains each failure, and returns a reviewable `PASS` or `HOLD` recommendation. It does not call a model, deploy a release, or claim semantic understanding.

## Workflow and architecture

1. Supply the same labeled case IDs to both experiment arms. Duplicate, missing and unexpected IDs reject the entire run.
2. Check exact answers, approved/required citations and abstention behavior. Case-level failure reasons remain inspectable.
3. Count paired wins, regressions, ties and critical failures; compute pass rates, measured cost and latency ratios.
4. Evaluate explicit quality, sample-size, critical-case, mean cost and mean latency gates.
5. Show uncertainty separately from acceptance gates: Wilson 95% score intervals for pass rates and an exact paired sign test on discordant outcomes.

The computation is pure Python with no dependencies or network requests. The caller supplies recorded model outputs and telemetry. The bundled six-case fixture is synthetic; it is not a measured production model comparison.

## Input contract

`SAMPLE` in `fieldkit/projects/evalforge.py` is the complete runnable example. The payload contains:

| Field | Meaning |
|---|---|
| `cases` | Unique `id`; either an exact `expected` answer or `abstain: true`; optional `critical` and citation allowlist |
| `baseline`, `candidate` | One result per `case_id`, with output, citations, abstention, measured `latency_ms` and `cost_usd` |
| `thresholds` | Minimum case count/pass rate/quality delta; maximum mean cost and latency ratios |

Exact-answer scoring strips leading/trailing whitespace only. Case, punctuation and internal whitespace remain significant. All provided citation IDs must be explicitly allowed. An abstention passes only when marked abstained with no answer or citations. Finite non-negative latency and cost are mandatory; booleans are not numbers.

## 90-second customer demo

1. Run the bundled sample: candidate passes 6/6, with two improvements over baseline and zero critical regressions.
2. Change the candidate answer for `refund-window` to `90 days`. The release holds and points directly to the critical regression.
3. Restore the answer and add `invented-policy` to its citations. Show why apparently correct prose still fails evidence validation.
4. Restore citations and increase all candidate latencies to 10,000 ms. Quality passes; the latency budget holds the release.
5. Delete one candidate result. Instead of reporting an inflated score, the run rejects mismatched experiment coverage.
6. Explain the wide interval for six cases. A demo pass is not statistical proof or permission to deploy.

## Reproducible checks

From the repository root:

```bash
python -m unittest discover -s tests -p test_evalforge.py -v
```

Tests cover correct pairing under reordering, critical regressions despite relaxed aggregate thresholds, omitted/duplicate cases, invented citations, unsafe abstention, zero baselines, latency budgets, non-finite measurements, threshold typos, minimum sample gates and known exact sign-test values.

## Decisions and limits

- Deterministic scoring is transparent and reproducible, but cannot accept a semantically equivalent paraphrase. Use task-specific structured outputs or reviewed labels; add a separately validated judge only where necessary.
- Wilson intervals are approximate and assume representative independent cases. Repeated templates or synthetic fixtures do not establish real-world generalization. The paired sign test ignores ties and severity; statistical results never override critical failures.
- Ratios against zero have no finite value when the candidate is positive, so the corresponding gate holds. If both measurements are zero, the ratio is neutral (1).
- Cost and latency are supplied telemetry, not independently verified by this engine. Mean latency can hide tail regressions; add p95/p99 and workload stratification before a production rollout.
- Dataset sizes are limited to 10,000 cases per run. No user authentication, managed experiment store, live model adapter or deployment integration is included in this module.

## Deployment and handoff backlog

Version datasets and labels; store immutable experiment manifests and model/prompt/tool versions; collect telemetry at the actual inference gateway; add domain/tenant slices and adversarial held-out cases; require independent review of labels and release overrides; connect recommendations to an authenticated deployment approval workflow. Keep model-provider integration outside the scorer so offline replay remains reproducible.

## Commercial hypothesis

A fixed-scope agent-release audit could package workflow discovery, a customer-reviewed acceptance set, baseline replay and release evidence. Validate willingness to pay with an actual pilot; this repository makes no savings, revenue or customer-adoption claims.
