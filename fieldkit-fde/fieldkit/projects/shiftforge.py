"""A bounded manufacturing scheduler with explicit infeasibility and downtime."""

import math
from collections import deque


SPEC = {
    "id": "shiftforge", "name": "ShiftForge", "track": "operations",
    "tagline": "Turn an overloaded order book into a feasible shift.",
    "description": "Schedule dependent manufacturing jobs against machine skills, release times and maintenance windows.",
    "customer": "A small manufacturer coordinating production and customer promises",
    "skills": ["DAG scheduling", "Capacity planning", "Explainability", "Constraint validation"],
    "flagship": False,
}

SAMPLE = {
    "horizon_minutes": 240,
    "machines": [
        {"id": "laser-1", "skills": ["cut"], "available_from": 0, "unavailable": [{"start": 60, "end": 90}]},
        {"id": "mill-1", "skills": ["mill", "drill"], "available_from": 0},
        {"id": "bench-1", "skills": ["assemble", "inspect"], "available_from": 15},
    ],
    "jobs": [
        {"id": "A-cut", "skill": "cut", "duration_minutes": 45, "due_minute": 60, "depends_on": []},
        {"id": "B-cut", "skill": "cut", "duration_minutes": 40, "due_minute": 100, "depends_on": []},
        {"id": "A-mill", "skill": "mill", "duration_minutes": 55, "due_minute": 115, "depends_on": ["A-cut"]},
        {"id": "A-assemble", "skill": "assemble", "duration_minutes": 35, "due_minute": 125, "depends_on": ["A-mill"]},
        {"id": "B-drill", "skill": "drill", "duration_minutes": 45, "due_minute": 160, "depends_on": ["B-cut"]},
        {"id": "B-inspect", "skill": "inspect", "duration_minutes": 20, "due_minute": 210, "depends_on": ["B-drill"]},
        {"id": "C-coat", "skill": "coat", "duration_minutes": 30, "due_minute": 180, "depends_on": []},
    ],
}


def _number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be a finite {'positive' if positive else 'nonnegative'} number")
    return float(value)


def _id(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise ValueError(f"{name} must be a nonempty identifier")
    return value


def _list(value, name, limit):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"{name} must contain at most {limit} records")
    if any(not isinstance(row, dict) for row in value):
        raise ValueError(f"Each {name} record must be an object")
    return value


def _slot(machine, ready, duration):
    start = max(ready, machine["available_from"])
    for window in machine["unavailable"]:
        if start + duration <= window["start"]:
            break
        if start < window["end"] and start + duration > window["start"]:
            start = window["end"]
    return start, start + duration


def run(payload):
    if not isinstance(payload, dict):
        raise ValueError("Input must be an object")
    horizon = _number(payload.get("horizon_minutes", 480), "horizon_minutes", True)
    machines = {}
    for row in _list(payload.get("machines"), "machines", 50):
        key = _id(row.get("id"), "machine id")
        if key in machines:
            raise ValueError(f"Duplicate machine: {key}")
        skills = row.get("skills")
        if not isinstance(skills, list) or not skills:
            raise ValueError("Each machine needs at least one skill")
        skills = {_id(skill, "skill") for skill in skills}
        available = _number(row.get("available_from", 0), "available_from")
        windows = []
        for interval in _list(row.get("unavailable", []), "unavailable", 100):
            start, end = _number(interval.get("start"), "maintenance start"), _number(interval.get("end"), "maintenance end")
            if end <= start:
                raise ValueError("Maintenance end must be after start")
            windows.append({"start": start, "end": end})
        windows.sort(key=lambda x: x["start"])
        if any(left["end"] > right["start"] for left, right in zip(windows, windows[1:])):
            raise ValueError("Maintenance intervals must not overlap")
        machines[key] = {"id": key, "skills": skills, "available_from": available, "unavailable": windows}
    if not machines:
        raise ValueError("At least one machine is required")
    jobs = {}
    for row in _list(payload.get("jobs"), "jobs", 200):
        key = _id(row.get("id"), "job id")
        if key in jobs:
            raise ValueError(f"Duplicate job: {key}")
        dependencies = row.get("depends_on", [])
        if not isinstance(dependencies, list):
            raise ValueError("depends_on must be a list")
        dependencies = [_id(d, "dependency") for d in dependencies]
        if len(dependencies) != len(set(dependencies)):
            raise ValueError("Duplicate job dependency")
        jobs[key] = {"id": key, "skill": _id(row.get("skill"), "skill"), "duration": _number(row.get("duration_minutes"), "duration_minutes", True), "release": _number(row.get("release_minute", 0), "release_minute"), "due": _number(row.get("due_minute", horizon), "due_minute"), "depends_on": dependencies}
    children = {key: [] for key in jobs}
    indegree = {key: len(row["depends_on"]) for key, row in jobs.items()}
    for key, row in jobs.items():
        for dependency in row["depends_on"]:
            if dependency not in jobs:
                raise ValueError(f"Unknown dependency: {dependency}")
            children[dependency].append(key)
    queue = deque(key for key, degree in indegree.items() if degree == 0)
    visited = 0
    degrees = indegree.copy()
    while queue:
        key = queue.popleft()
        visited += 1
        for child in children[key]:
            degrees[child] -= 1
            if degrees[child] == 0:
                queue.append(child)
    if visited != len(jobs):
        raise ValueError("Job dependency cycle detected; a feasible ordering cannot be established")
    remaining, completed, rejected, records = set(jobs), {}, {}, []
    machine_clock = {key: row["available_from"] for key, row in machines.items()}
    while remaining:
        ready = sorted((jobs[key] for key in remaining if all(d in completed or d in rejected for d in jobs[key]["depends_on"])), key=lambda row: (row["due"], row["release"], row["id"]))
        job = ready[0]
        key = job["id"]
        remaining.remove(key)
        blockers = [d for d in job["depends_on"] if d in rejected]
        if blockers:
            rejected[key] = {"job": key, "reason": "blocked_dependency", "dependencies": blockers}
            continue
        qualified = [machine for machine in machines.values() if job["skill"] in machine["skills"]]
        if not qualified:
            rejected[key] = {"job": key, "reason": "missing_machine_skill", "skill": job["skill"]}
            continue
        release = max([job["release"]] + [completed[d]["end_minute"] for d in job["depends_on"]])
        options = []
        for machine in qualified:
            start, end = _slot(machine, max(release, machine_clock[machine["id"]]), job["duration"])
            if end <= horizon:
                options.append((end, start, machine["id"]))
        if not options:
            rejected[key] = {"job": key, "reason": "planning_horizon_capacity", "earliest_release_minute": release, "duration_minutes": job["duration"]}
            continue
        end, start, machine_id = min(options)
        record = {"job": key, "machine": machine_id, "skill": job["skill"], "start_minute": start, "end_minute": end, "duration_minutes": job["duration"], "due_minute": job["due"], "late_minutes": max(0, end - job["due"]), "depends_on": job["depends_on"]}
        records.append(record)
        completed[key], machine_clock[machine_id] = record, end
    summaries = []
    for key, machine in sorted(machines.items()):
        capacity = max(0, horizon - machine["available_from"])
        downtime = sum(max(0, min(horizon, w["end"]) - max(machine["available_from"], w["start"])) for w in machine["unavailable"])
        capacity = max(0, capacity - downtime)
        assigned = [row for row in records if row["machine"] == key]
        busy = sum(row["duration_minutes"] for row in assigned)
        summaries.append({"machine": key, "scheduled_jobs": len(assigned), "busy_minutes": busy, "available_minutes": capacity, "maintenance_minutes": downtime, "utilization_pct": round(100 * busy / capacity, 2) if capacity else 0, "unavailable": machine["unavailable"]})
    bottlenecks = sorted(summaries, key=lambda r: (-r["utilization_pct"], r["machine"]))
    records.sort(key=lambda row: (row["start_minute"], row["machine"], row["job"]))
    late = sum(row["late_minutes"] > 0 for row in records)
    return {
        "summary": f"Scheduled {len(records)}/{len(jobs)} jobs; {late} finish late and {len(rejected)} need production-planner review.",
        "metrics": {"scheduled_jobs": len(records), "unscheduled_jobs": len(rejected), "late_jobs": late, "total_lateness_minutes": sum(row["late_minutes"] for row in records), "makespan_minutes": max((row["end_minute"] for row in records), default=0)},
        "records": records, "warnings": ["This deterministic earliest-due-date list scheduler produces a feasible plan, not an optimal schedule.", "One job occupies one machine at a time. Setup, transport, labor pools and material availability are not modeled."],
        "unscheduled": list(rejected.values()), "machines": summaries, "bottleneck_candidates": bottlenecks[:3], "horizon_minutes": horizon,
    }
