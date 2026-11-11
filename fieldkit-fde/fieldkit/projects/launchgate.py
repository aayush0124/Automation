"""Evidence-based canary decisions from supplied counters and latency samples."""
from __future__ import annotations

import math
from typing import Any

SPEC = {
    "id": "launchgate", "name": "LaunchGate", "track": "reliability",
    "tagline": "A release decision that explains its evidence.",
    "description": "An inspectable canary gate combining traffic sufficiency, SLO burn, latency and baseline regression.",
    "customer": "A platform team deciding whether to expand, pause or roll back a customer-facing release.",
    "skills": ["SLOs", "canary releases", "error budgets", "latency analysis", "operational handoff"],
    "flagship": False,
}

SAMPLE = {
    "baseline": {"requests": 1200, "errors": 3, "window_minutes": 10,
                 "latency_ms": [95, 100, 110, 105, 115, 120, 100, 110, 130, 115, 105, 100, 120, 135, 110, 120, 115, 125, 140, 150]},
    "canary": {"requests": 400, "errors": 14, "window_minutes": 10,
               "latency_ms": [100, 110, 130, 140, 150, 155, 160, 165, 170, 175, 180, 190, 210, 230, 250, 270, 300, 380, 420, 900]},
    "policy": {"min_requests": 200, "min_latency_samples": 20, "success_slo": 0.99,
               "max_burn_rate": 2.0, "max_error_increase_pp": 1.0, "max_p95_ms": 500,
               "max_latency_ratio": 1.5, "budget_period_days": 30},
}


def _number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be a finite number between {minimum} and {maximum}")
    return float(value)


def _integer(value: Any, name: str, minimum: int, maximum: int = 1000000000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile; a p95 from 20 observations is the 19th sorted value."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _window(value: Any, name: str, policy: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    requests = _integer(value.get("requests"), f"{name}.requests", 0)
    errors = _integer(value.get("errors"), f"{name}.errors", 0, requests)
    minutes = _number(value.get("window_minutes"), f"{name}.window_minutes", 0.001, 10080)
    samples = value.get("latency_ms")
    if not isinstance(samples, list) or len(samples) > min(requests, 100000):
        raise ValueError(f"{name}.latency_ms must be a list with at most min(requests,100000) samples")
    samples = [_number(v, f"{name}.latency_ms", 0, 3600000) for v in samples]
    rate = errors / requests if requests else None
    allowed = 1 - policy["success_slo"]
    burn = rate / allowed if rate is not None else None
    budget_minutes = policy["budget_period_days"] * 1440
    return {"requests": requests, "errors": errors, "window_minutes": minutes, "latency_samples": len(samples),
            "error_rate": rate, "error_rate_percent": round(rate * 100, 6) if rate is not None else None,
            "burn_rate": burn,
            "p50_ms": percentile(samples, .50), "p95_ms": percentile(samples, .95), "p99_ms": percentile(samples, .99),
            "projected_budget_consumption_percent": round(burn * minutes / budget_minutes * 100, 6) if burn is not None else None}


def run(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    supplied = payload.get("policy", {})
    if not isinstance(supplied, dict):
        raise ValueError("policy must be an object")
    defaults = {"min_requests": 200, "min_latency_samples": 20, "success_slo": .99, "max_burn_rate": 2.,
                "max_error_increase_pp": 1., "max_p95_ms": 500., "max_latency_ratio": 1.5, "budget_period_days": 30.}
    unknown = set(supplied) - set(defaults)
    if unknown:
        raise ValueError(f"unknown policy fields: {', '.join(sorted(unknown))}")
    policy = {**defaults, **supplied}
    policy["min_requests"] = _integer(policy["min_requests"], "min_requests", 1)
    policy["min_latency_samples"] = _integer(policy["min_latency_samples"], "min_latency_samples", 1, 100000)
    for key, low, high in (("success_slo", .5, .999999), ("max_burn_rate", .01, 10000),
                           ("max_error_increase_pp", 0, 100), ("max_p95_ms", .001, 3600000),
                           ("max_latency_ratio", 1, 1000), ("budget_period_days", 1, 365)):
        policy[key] = _number(policy[key], key, low, high)
    baseline = _window(payload.get("baseline"), "baseline", policy)
    canary = _window(payload.get("canary"), "canary", policy)
    checks = []

    def check(name: str, outcome: str, observed: Any, threshold: Any, reason: str) -> None:
        checks.append({"check": name, "outcome": outcome, "observed": observed, "threshold": threshold, "reason": reason})

    traffic_ready = all(w["requests"] >= policy["min_requests"] for w in (baseline, canary))
    samples_ready = all(w["latency_samples"] >= policy["min_latency_samples"] for w in (baseline, canary))
    check("Traffic sufficiency", "pass" if traffic_ready else "hold", min(baseline["requests"], canary["requests"]), policy["min_requests"],
          "Both cohorts must meet the configured minimum request count.")
    check("Latency sample sufficiency", "pass" if samples_ready else "hold", min(baseline["latency_samples"], canary["latency_samples"]), policy["min_latency_samples"],
          "Both cohorts need enough latency observations; missing samples cannot pass.")
    comparable = baseline["window_minutes"] == canary["window_minutes"]
    check("Comparable windows", "pass" if comparable else "hold", [baseline["window_minutes"], canary["window_minutes"]], "equal minutes",
          "Unequal windows require re-aggregation before an automatic comparison.")
    error_delta = None
    if canary["error_rate"] is not None and baseline["error_rate"] is not None:
        error_delta = (canary["error_rate"] - baseline["error_rate"]) * 100
    latency_ratio = None
    if canary["p95_ms"] is not None and baseline["p95_ms"] not in (None, 0):
        latency_ratio = canary["p95_ms"] / baseline["p95_ms"]
    gates = [
        ("Canary error-budget burn", canary["burn_rate"], policy["max_burn_rate"], traffic_ready,
         "Observed error fraction divided by the allowed SLO error fraction."),
        ("Error regression (percentage points)", error_delta, policy["max_error_increase_pp"], traffic_ready and comparable,
         "Absolute canary-minus-baseline error-rate increase, in percentage points."),
        ("Canary p95 latency (ms)", canary["p95_ms"], policy["max_p95_ms"], samples_ready,
         "Nearest-rank p95 from supplied observations; not an extrapolated distribution."),
        ("p95 latency ratio", latency_ratio, policy["max_latency_ratio"], samples_ready and comparable,
         "Canary p95 divided by baseline p95; a zero baseline cannot form a meaningful ratio."),
    ]
    for name, value, limit, ready, reason in gates:
        outcome = "hold" if not ready or value is None else ("fail" if value > limit else "pass")
        check(name, outcome, round(value, 6) if value is not None else None, limit, reason)
    # A sufficiently measured failure is actionable even if another independent gate lacks data.
    failures = [r["check"] for r in checks if r["outcome"] == "fail"]
    holds = [r["check"] for r in checks if r["outcome"] == "hold"]
    decision = "rollback" if failures else "hold" if holds else "approve"
    explanation = {"rollback": "Measured thresholds were exceeded; recommend restoring the previous release.",
                   "hold": "Evidence is insufficient or not comparable; keep the present canary exposure.",
                   "approve": "All supplied evidence passes policy; recommend the next bounded rollout stage."}[decision]
    warnings = ["Decision support only: no deployment or rollback is executed.",
                "Synthetic fixture by default. This threshold gate does not establish statistical significance or causal impact.",
                "Budget consumption is a constant-traffic projection from this window, not measured monthly budget remaining."]
    if baseline["burn_rate"] is not None and baseline["burn_rate"] > policy["max_burn_rate"]:
        warnings.append("Baseline also exceeds the burn threshold; investigate shared infrastructure before attributing failures to the release.")
    return {"summary": f"{decision.upper()}: {explanation}",
            "metrics": {"decision": decision, "passed_checks": sum(r["outcome"] == "pass" for r in checks),
                        "failed_checks": len(failures), "held_checks": len(holds), "canary_requests": canary["requests"],
                        "canary_burn_rate": canary["burn_rate"], "canary_p95_ms": canary["p95_ms"]},
            "records": checks, "warnings": warnings, "decision": decision,
            "baseline": baseline, "canary": canary, "policy": policy, "failures": failures, "holds": holds,
            "data_mode": "supplied counters and latency samples; default fixture is synthetic"}
