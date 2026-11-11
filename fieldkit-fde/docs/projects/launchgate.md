# LaunchGate — the evidence-based release desk

## Customer problem

A platform team has a small canary release and a noisy incident channel. The team needs an explainable decision about expanding, holding or reverting exposure. Comparing a few successful requests or unrelated time windows can create false confidence. LaunchGate turns supplied counters and latency observations into an inspectable release recommendation.

The default dataset is synthetic. The system never deploys software or executes a rollback.

## Working implementation

`fieldkit/projects/launchgate.py` validates baseline and canary request/error counters, observation windows and millisecond latency samples. Both cohorts must meet configurable request and sample minimums. Relative comparisons require equal window durations. Latency uses the documented nearest-rank percentile algorithm, not interpolation or an invented distribution.

The gate evaluates canary error-budget burn, absolute error-rate regression in percentage points, absolute p95 latency and p95 ratio against baseline. A sufficiently observed failure recommends `rollback`, even if another independent signal lacks data. Insufficient or incomparable evidence produces `hold`; all passing gates produce `approve` for the next bounded rollout stage.

Burn rate is `observed error fraction / (1 - success SLO)`. Projected budget consumption is `burn rate × observed window minutes / budget-period minutes`. This is a constant-traffic projection, not measured remaining monthly budget. No cohort randomization, confidence interval, significance test or causal claim is implemented.

## Input contract

```json
{
  "baseline": {"requests": 500, "errors": 1, "window_minutes": 10,
               "latency_ms": [100, 110, 120]},
  "canary": {"requests": 250, "errors": 1, "window_minutes": 10,
             "latency_ms": [105, 115, 125]},
  "policy": {"min_requests": 200, "min_latency_samples": 3,
             "success_slo": 0.99, "max_burn_rate": 2,
             "max_error_increase_pp": 1, "max_p95_ms": 500,
             "max_latency_ratio": 1.5, "budget_period_days": 30}
}
```

The deliberately tiny example above illustrates schema only; a three-sample percentile is not reliable production evidence. The default fixture uses 20 observations per cohort and still has the limitations of a small synthetic sample. Production thresholds require customer-specific analysis.

Counters must be nonnegative integers with errors no greater than requests. Samples must be finite nonnegative millisecond values, with no more samples than requests. Units are explicit in field names. NaN, infinity, bool-as-integer and unknown policy fields are rejected. Zero baseline p95 cannot yield a meaningful latency ratio and therefore holds that comparison.

## 90-second demo

1. Run the fixture. Explain the rollback recommendation using the 3.5× canary burn rate and p95 regression; the values are computed from the supplied data.
2. Change canary errors to one and replace its latency samples with 20 values of 100 ms. Show a passing next-stage recommendation.
3. Set canary traffic to zero and its samples to an empty list. Show `hold`, null rates and missing-evidence explanations, not a divide-by-zero or an approval.
4. Change only the canary observation window to five minutes. Show why relative comparisons hold until cohorts are re-aggregated.

## Acceptance evidence

Run `python -m unittest discover -s tests -p test_launchgate.py -v` from the repository root. Tests cover rollback and approval paths, zero traffic, insufficient cohorts, absent latency, independent rollback signals, unequal windows, zero latency baselines, nearest-rank behavior, percentage-point units, budget-period arithmetic and rejected invalid values.

The metrics are supplied-cohort calculations and check counts. They do not establish real release safety, customer adoption or production uptime.

## Deployment tradeoffs and limits

A threshold engine is easy to inspect and replay, but cannot distinguish a code regression from a shared outage or biased cohorts. The output warns when baseline burn is also excessive. Equal window duration alone does not prove aligned timestamps or equivalent populations; production ingestion must validate window boundaries, cohorts, data freshness and sampling policy.

Before live use: connect authenticated telemetry, add time-aligned rolling windows, multiple-window burn alerts, statistical uncertainty and cohort analysis, durable decision/audit records, role-bound approvals, rollout-controller integration, stale-data rejection and a tested rollback playbook. Account for request volume variation when calculating actual error-budget remaining. A human owns the release decision until those controls are validated.

## Commercial hypothesis

Offer a release-readiness and canary-observability package to B2B SaaS teams with frequent customer deployments. Validate demand with historical incident replays and measure alert usefulness, rollback delay and false holds before making any savings claims.
