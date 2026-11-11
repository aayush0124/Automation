"""Paired, deterministic acceptance evaluation for an agent release.

This module evaluates supplied outputs. It never invokes or claims to be an LLM
judge. Fixtures are synthetic and customer savings are deliberately not inferred.
"""

from __future__ import annotations

import math
from statistics import mean
from typing import Any


SPEC = {
    "id": "evalforge",
    "name": "EvalForge",
    "track": "reliability",
    "tagline": "Make the release decision explain itself.",
    "description": "A paired acceptance bench that gates agent changes on answers, evidence, abstention, critical failures, cost and latency.",
    "customer": "Enterprise AI teams replacing an agent or changing its prompts and tools.",
    "skills": ["Agent evaluation", "Paired experiments", "Release gates", "Failure analysis", "Cost and latency"],
    "flagship": True,
}

SAMPLE = {
    "dataset": "Synthetic support-policy acceptance set; not customer data",
    "cases": [
        {"id": "refund-window", "expected": "30 days", "required_citations": ["refund-v3"], "critical": True},
        {"id": "refund-opened", "expected": "Review required", "required_citations": ["refund-v3"]},
        {"id": "billing-date", "expected": "First business day", "required_citations": ["billing-v2"]},
        {"id": "private-account", "abstain": True, "critical": True},
        {"id": "missing-policy", "abstain": True},
        {"id": "export-format", "expected": "CSV", "required_citations": ["export-v1"]},
    ],
    "baseline": [
        {"case_id": "refund-window", "output": "30 days", "citations": ["refund-v3"], "latency_ms": 420, "cost_usd": 0.003},
        {"case_id": "refund-opened", "output": "Refund approved", "citations": ["refund-v3"], "latency_ms": 510, "cost_usd": 0.004},
        {"case_id": "billing-date", "output": "First business day", "citations": [], "latency_ms": 450, "cost_usd": 0.003},
        {"case_id": "private-account", "output": "", "abstained": True, "latency_ms": 190, "cost_usd": 0.001},
        {"case_id": "missing-policy", "output": "", "abstained": True, "latency_ms": 220, "cost_usd": 0.001},
        {"case_id": "export-format", "output": "CSV", "citations": ["export-v1"], "latency_ms": 340, "cost_usd": 0.002},
    ],
    "candidate": [
        {"case_id": "refund-window", "output": "30 days", "citations": ["refund-v3"], "latency_ms": 360, "cost_usd": 0.003},
        {"case_id": "refund-opened", "output": "Review required", "citations": ["refund-v3"], "latency_ms": 430, "cost_usd": 0.004},
        {"case_id": "billing-date", "output": "First business day", "citations": ["billing-v2"], "latency_ms": 390, "cost_usd": 0.003},
        {"case_id": "private-account", "output": "", "abstained": True, "latency_ms": 170, "cost_usd": 0.001},
        {"case_id": "missing-policy", "output": "", "abstained": True, "latency_ms": 190, "cost_usd": 0.001},
        {"case_id": "export-format", "output": "CSV", "citations": ["export-v1"], "latency_ms": 300, "cost_usd": 0.002},
    ],
    "thresholds": {"min_cases": 5, "min_pass_rate": 0.9, "min_quality_delta": 0.0, "max_cost_ratio": 1.15, "max_latency_ratio": 1.2},
}


def _number(value: Any, name: str, minimum: float = 0, maximum: float = math.inf) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be representable as a finite number") from exc
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be finite and between {minimum} and {maximum}")
    return value


def _strings(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f"{name} must be a list of non-empty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{name} cannot contain duplicates")
    return value


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _index(rows: Any, key: str, name: str) -> dict[str, dict]:
    if not isinstance(rows, list) or not rows or len(rows) > 10000:
        raise ValueError(f"{name} must contain 1 to 10000 records")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError(f"Every {name} record needs a non-empty {key}")
        if row[key] in result:
            raise ValueError(f"Duplicate {key} in {name}: {row[key]}")
        result[row[key]] = row
    return result


def _score(case: dict, result: dict) -> dict:
    abstain = _boolean(case.get("abstain", False), "case.abstain")
    expected = case.get("expected", "")
    if not isinstance(expected, str) or (not abstain and not expected.strip()):
        raise ValueError("Non-abstention cases require a non-empty exact expected answer")
    output = result.get("output", "")
    if not isinstance(output, str):
        raise ValueError("result.output must be a string")
    abstained = _boolean(result.get("abstained", False), "result.abstained")
    required = set(_strings(case.get("required_citations", []), "required_citations"))
    allowed = set(_strings(case.get("allowed_citations", list(required)), "allowed_citations"))
    if not required <= allowed:
        raise ValueError("required_citations must be included in allowed_citations")
    citations = set(_strings(result.get("citations", []), "citations"))
    reasons = []
    if abstain:
        if not abstained or output.strip() or citations:
            reasons.append("Expected abstention without answer or citations")
    else:
        if abstained:
            reasons.append("Unexpected abstention")
        if output.strip() != expected.strip():
            reasons.append("Exact answer mismatch")
        if required - citations:
            reasons.append("Missing required citations: " + ", ".join(sorted(required - citations)))
        if citations - allowed:
            reasons.append("Unapproved citations: " + ", ".join(sorted(citations - allowed)))
    return {
        "passed": not reasons,
        "reasons": reasons,
        "latency_ms": _number(result.get("latency_ms"), "latency_ms", 0, 1e12),
        "cost_usd": _number(result.get("cost_usd"), "cost_usd", 0, 1e9),
    }


def _wilson(successes: int, total: int) -> list[float]:
    """Wilson 95% score interval; descriptive, not a release guarantee."""
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [round(max(0, centre - spread), 6), round(min(1, centre + spread), 6)]


def _ratio(candidate: float, baseline: float) -> float | None:
    if baseline == 0:
        return 1.0 if candidate == 0 else None
    ratio = candidate / baseline
    return ratio if math.isfinite(ratio) else None


def _sign_test(wins: int, losses: int) -> float:
    """Two-sided exact sign test among discordant pairs only."""
    n = wins + losses
    if not n:
        return 1.0
    # Recurrence avoids conversion of enormous binomial integers to float.
    log_terms = [math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) - n * math.log(2)
                 for k in range(min(wins, losses) + 1)]
    return min(1.0, 2 * sum(math.exp(term) for term in log_terms))


def run(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    cases = _index(payload.get("cases"), "id", "cases")
    baseline = _index(payload.get("baseline"), "case_id", "baseline")
    candidate = _index(payload.get("candidate"), "case_id", "candidate")
    for name, rows in (("baseline", baseline), ("candidate", candidate)):
        if rows.keys() != cases.keys():
            missing, extra = sorted(cases.keys() - rows.keys()), sorted(rows.keys() - cases.keys())
            raise ValueError(f"{name} case alignment failed; missing={missing}, extra={extra}")
    thresholds = payload.get("thresholds", {})
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds must be an object")
    known_thresholds = {"min_cases", "min_pass_rate", "min_quality_delta", "max_cost_ratio", "max_latency_ratio"}
    if set(thresholds) - known_thresholds:
        raise ValueError("Unknown threshold: " + ", ".join(sorted(set(thresholds) - known_thresholds)))
    limits = {
        "min_cases": _number(thresholds.get("min_cases", 5), "min_cases", 1, 10000),
        "min_pass_rate": _number(thresholds.get("min_pass_rate", 0.9), "min_pass_rate", 0, 1),
        "min_quality_delta": _number(thresholds.get("min_quality_delta", 0), "min_quality_delta", -1, 1),
        "max_cost_ratio": _number(thresholds.get("max_cost_ratio", 1.15), "max_cost_ratio"),
        "max_latency_ratio": _number(thresholds.get("max_latency_ratio", 1.2), "max_latency_ratio"),
    }
    if limits["min_cases"] != int(limits["min_cases"]):
        raise ValueError("min_cases must be an integer")
    records = []
    for case_id, case in cases.items():
        critical = _boolean(case.get("critical", False), "critical")
        before, after = _score(case, baseline[case_id]), _score(case, candidate[case_id])
        records.append({"case_id": case_id, "critical": critical, "baseline_pass": before["passed"],
                        "candidate_pass": after["passed"], "change": int(after["passed"]) - int(before["passed"]),
                        "candidate_failures": after["reasons"], "baseline_failures": before["reasons"],
                        "baseline_latency_ms": before["latency_ms"], "candidate_latency_ms": after["latency_ms"],
                        "baseline_cost_usd": before["cost_usd"], "candidate_cost_usd": after["cost_usd"]})
    n = len(records)
    base_pass = sum(r["baseline_pass"] for r in records)
    cand_pass = sum(r["candidate_pass"] for r in records)
    cost_before = mean(r["baseline_cost_usd"] for r in records)
    cost_after = mean(r["candidate_cost_usd"] for r in records)
    latency_before = mean(r["baseline_latency_ms"] for r in records)
    latency_after = mean(r["candidate_latency_ms"] for r in records)
    cost_ratio, latency_ratio = _ratio(cost_after, cost_before), _ratio(latency_after, latency_before)
    critical_failures = [r["case_id"] for r in records if r["critical"] and not r["candidate_pass"]]
    wins, losses = sum(r["change"] == 1 for r in records), sum(r["change"] == -1 for r in records)
    delta = (cand_pass - base_pass) / n
    gates = [
        {"gate": "minimum_cases", "passed": n >= limits["min_cases"], "actual": n, "threshold": limits["min_cases"]},
        {"gate": "candidate_pass_rate", "passed": cand_pass / n >= limits["min_pass_rate"], "actual": cand_pass / n, "threshold": limits["min_pass_rate"]},
        {"gate": "paired_quality_delta", "passed": delta >= limits["min_quality_delta"], "actual": delta, "threshold": limits["min_quality_delta"]},
        {"gate": "critical_cases", "passed": not critical_failures, "actual": len(critical_failures), "threshold": 0},
        {"gate": "mean_cost_ratio", "passed": cost_ratio is not None and cost_ratio <= limits["max_cost_ratio"], "actual": cost_ratio, "threshold": limits["max_cost_ratio"]},
        {"gate": "mean_latency_ratio", "passed": latency_ratio is not None and latency_ratio <= limits["max_latency_ratio"], "actual": latency_ratio, "threshold": limits["max_latency_ratio"]},
    ]
    decision = "PASS" if all(g["passed"] for g in gates) else "HOLD"
    warnings = ["Deterministic exact-answer and citation checks; this is not an LLM judge or a semantic quality guarantee.",
                "Evaluation approval is not deployment authorization. Representative production data and independent review are still required."]
    if n < 30:
        warnings.append("Small evaluation set: uncertainty is high; do not interpret a passing gate as statistical evidence of general improvement.")
    if cost_ratio is None or latency_ratio is None:
        warnings.append("A ratio is non-finite because the baseline is zero or too small to represent the ratio; its gate is held.")
    return {
        "summary": f"{decision}: {cand_pass}/{n} candidate cases pass; {wins} paired wins, {losses} regressions, {len(critical_failures)} critical failures.",
        "metrics": {"cases": n, "baseline_pass_rate": round(base_pass / n, 6), "candidate_pass_rate": round(cand_pass / n, 6),
                    "quality_delta": round(delta, 6), "paired_wins": wins, "paired_losses": losses, "paired_ties": n - wins - losses,
                    "critical_failures": len(critical_failures), "mean_cost_ratio": cost_ratio, "mean_latency_ratio": latency_ratio,
                    "candidate_total_cost_usd": round(sum(r["candidate_cost_usd"] for r in records), 9),
                    "candidate_mean_latency_ms": round(latency_after, 3)},
        "records": records, "warnings": warnings, "decision": decision, "gates": gates,
        "critical_failure_ids": critical_failures,
        "uncertainty": {"method": "Wilson 95% score intervals for each pass rate; exact two-sided sign test on discordant pairs",
                        "baseline_pass_rate_95_interval": _wilson(base_pass, n),
                        "candidate_pass_rate_95_interval": _wilson(cand_pass, n),
                        "paired_sign_test_p_value": round(_sign_test(wins, losses), 6),
                        "used_for_gate": False,
                        "caveat": "Assumes representative independent cases; correlated templates reduce effective sample size. Intervals are approximate; sign test discards ties and ignores effect severity."},
        "data_note": "Inputs are supplied evaluation evidence; the bundled sample is entirely synthetic.",
    }
