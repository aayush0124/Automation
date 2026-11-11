"""Evidence-led incident triage on a customer service dependency graph."""

from collections import deque
import math


SPEC = {
    "id": "switchboard", "name": "Switchboard", "track": "operations",
    "tagline": "Find the blast radius before proposing the fix.",
    "description": "Correlate service failures, dependency impact and recent deploys in a reviewable incident brief.",
    "customer": "A SaaS platform's on-call engineering team",
    "skills": ["Dependency graphs", "Incident analysis", "Evidence provenance", "Safe operations"],
    "flagship": False,
}

SAMPLE = {
    "now_minute": 600, "correlation_window_minutes": 30, "alert_threshold_pct": 5,
    "services": [
        {"id": "checkout", "depends_on": ["orders", "payments"], "error_rate_pct": 24, "traffic_rpm": 420},
        {"id": "orders", "depends_on": ["database"], "error_rate_pct": 16, "traffic_rpm": 650},
        {"id": "payments", "depends_on": ["database"], "error_rate_pct": 18, "traffic_rpm": 310},
        {"id": "database", "depends_on": [], "error_rate_pct": 38, "traffic_rpm": 1200},
        {"id": "catalog", "depends_on": ["cache"], "error_rate_pct": 0.4, "traffic_rpm": 900},
        {"id": "cache", "depends_on": [], "error_rate_pct": 0.1, "traffic_rpm": 1000},
    ],
    "deployments": [
        {"service": "database", "minute": 588, "version": "pool-config-17"},
        {"service": "checkout", "minute": 410, "version": "checkout-42"},
    ],
}


def _number(value, name, low=0, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < low or (high is not None and value > high):
        raise ValueError(f"{name} is outside its allowed range")
    return float(value)


def _identifier(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise ValueError(f"{name} must be a nonempty string of at most 120 characters")
    return value


def _cycle_edges(services):
    state, edges = {}, []

    def visit(node):
        state[node] = 1
        for child in services[node]["depends_on"]:
            if state.get(child) == 1:
                edges.append([node, child])
            elif not state.get(child):
                visit(child)
        state[node] = 2

    for node in sorted(services):
        if not state.get(node):
            visit(node)
    return edges


def run(payload):
    """Rank hypotheses; never assert a cause or execute a remediation."""
    if not isinstance(payload, dict):
        raise ValueError("Input must be an object")
    raw = payload.get("services")
    if not isinstance(raw, list) or len(raw) > 200:
        raise ValueError("services must be a list containing at most 200 services")
    now = _number(payload.get("now_minute", 0), "now_minute")
    window = _number(payload.get("correlation_window_minutes", 30), "correlation_window_minutes")
    threshold = _number(payload.get("alert_threshold_pct", 5), "alert_threshold_pct", 0, 100)
    services = {}
    for row in raw:
        if not isinstance(row, dict):
            raise ValueError("Each service must be an object")
        service_id = _identifier(row.get("id"), "service id")
        if service_id in services:
            raise ValueError(f"Duplicate service: {service_id}")
        dependencies = row.get("depends_on", [])
        if not isinstance(dependencies, list) or any(not isinstance(x, str) for x in dependencies):
            raise ValueError("depends_on must be a list of service identifiers")
        if len(dependencies) != len(set(dependencies)):
            raise ValueError(f"Duplicate dependency for {service_id}")
        services[service_id] = {
            "depends_on": dependencies,
            "error_rate_pct": _number(row.get("error_rate_pct"), "error_rate_pct", 0, 100),
            "traffic_rpm": _number(row.get("traffic_rpm", 0), "traffic_rpm"),
        }
    dependents = {key: [] for key in services}
    for key, row in services.items():
        for dependency in row["depends_on"]:
            if dependency not in services:
                raise ValueError(f"Unknown dependency {dependency} on {key}")
            dependents[dependency].append(key)
    raw_deployments = payload.get("deployments", [])
    if not isinstance(raw_deployments, list) or len(raw_deployments) > 1000:
        raise ValueError("deployments must contain at most 1000 records")
    recent = {key: [] for key in services}
    warnings = ["Hypothesis scores are deterministic heuristics, not causal proof or calibrated probabilities."]
    for deployment in raw_deployments:
        if not isinstance(deployment, dict):
            raise ValueError("Each deployment must be an object")
        service = _identifier(deployment.get("service"), "deployment service")
        if service not in services:
            raise ValueError(f"Unknown deployment service: {service}")
        minute = _number(deployment.get("minute"), "deployment minute")
        version = _identifier(deployment.get("version"), "deployment version")
        age = now - minute
        if age < 0:
            warnings.append(f"Ignored future deployment {version} for {service}.")
        elif age <= window:
            recent[service].append({"version": version, "age_minutes": age, "minute": minute})
    cycles = _cycle_edges(services)
    if cycles:
        warnings.append("Dependency cycles detected; blast-radius traversal uses a visited set.")
    alerted = {key for key, row in services.items() if row["error_rate_pct"] >= threshold}
    records = []
    for key in sorted(alerted):
        seen, queue = {key}, deque([key])
        while queue:
            for dependent in dependents[queue.popleft()]:
                if dependent not in seen:
                    seen.add(dependent)
                    queue.append(dependent)
        downstream = sorted(seen - {key})
        corroborated = sorted((seen - {key}) & alerted)
        failed_dependencies = sorted(set(services[key]["depends_on"]) & alerted)
        own_error = services[key]["error_rate_pct"]
        score = round(max(0, own_error + 5 * len(corroborated) + (10 if recent[key] else 0) - 8 * len(failed_dependencies)), 2)
        records.append({
            "service": key, "hypothesis_score": score, "error_rate_pct": own_error,
            "potentially_affected_services": downstream, "alerting_dependents": corroborated,
            "unhealthy_dependencies": failed_dependencies, "recent_deployments": recent[key],
            "estimated_failed_requests_per_minute": round(services[key]["traffic_rpm"] * own_error / 100, 2),
            "evidence": [f"Observed error rate {own_error:g}%", f"{len(corroborated)} downstream services also alerting", f"{len(recent[key])} deployment(s) in the correlation window", f"{len(failed_dependencies)} unhealthy direct dependencies"],
        })
    records.sort(key=lambda row: (-row["hypothesis_score"], row["service"]))
    plan = []
    for rank, candidate in enumerate(records[:3], 1):
        plan.append({
            "priority": rank, "service": candidate["service"], "status": "review_required",
            "next_step": "Compare traces and dependency health; verify the hypothesis before changing the system.",
            "change_review": "Review recent deployment diff and prepare an approved rollback only if evidence confirms it." if candidate["recent_deployments"] else "Inspect recent configuration and resource saturation; no temporal deployment evidence is available.",
        })
    return {
        "summary": f"{len(alerted)} of {len(services)} services are alerting; {records[0]['service']} is the highest-ranked hypothesis." if records else "No service meets the configured alert threshold.",
        "metrics": {"services": len(services), "alerting_services": len(alerted), "cycle_edges": len(cycles), "recent_deployments": sum(map(len, recent.values()))},
        "records": records, "warnings": warnings, "response_plan": plan, "mode": "dry_run",
        "graph": {"nodes": sorted(services), "edges": [{"service": key, "depends_on": dependency} for key, row in services.items() for dependency in row["depends_on"]], "cycle_edges": cycles},
        "score_formula": "max(0, own error percentage + 5 * alerting downstream services + 10 if recent deployment - 8 * unhealthy direct dependencies)",
    }
