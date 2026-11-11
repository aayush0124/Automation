"""Small-fleet delivery planning with capacity and service-completion windows."""

import math


SPEC = {
    "id": "routecraft", "name": "RouteCraft", "track": "operations",
    "tagline": "Make promises the fleet can actually keep.",
    "description": "Construct feasible delivery routes and explain every unassigned job under capacity, time-window and shift constraints.",
    "customer": "A regional distributor planning a small delivery fleet",
    "skills": ["Constraint modeling", "Routing heuristics", "Operational tradeoffs", "Baseline evaluation"],
    "flagship": False,
}

SAMPLE = {
    "depot": [0, 0],
    "vehicles": [
        {"id": "van-1", "capacity": 8, "shift_start": 0, "shift_end": 90, "speed_units_per_minute": 1},
        {"id": "van-2", "capacity": 6, "shift_start": 0, "shift_end": 70, "speed_units_per_minute": 1},
    ],
    "jobs": [
        {"id": "tea-shop", "location": [12, 4], "demand": 3, "window_start": 20, "window_end": 55, "service_minutes": 5},
        {"id": "bakery", "location": [3, 4], "demand": 2, "window_start": 0, "window_end": 20, "service_minutes": 4},
        {"id": "grocer", "location": [10, 8], "demand": 3, "window_start": 15, "window_end": 50, "service_minutes": 5},
        {"id": "cafe", "location": [4, 2], "demand": 2, "window_start": 5, "window_end": 25, "service_minutes": 3},
        {"id": "wholesaler", "location": [6, 6], "demand": 12, "window_start": 0, "window_end": 60, "service_minutes": 8},
        {"id": "distant-kiosk", "location": [90, 0], "demand": 1, "window_start": 0, "window_end": 25, "service_minutes": 2},
    ],
}


def _number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be a finite {'positive' if positive else 'nonnegative'} number")
    return float(value)


def _point(value, name):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} must be [x, y]")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError(f"{name} coordinates must be finite numbers")
    return [float(v) for v in value]


def _rows(value, name, maximum):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{name} must be a list with at most {maximum} rows")
    seen = set()
    for row in value:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip() or len(row["id"]) > 120:
            raise ValueError(f"Each {name} row needs a nonempty id")
        if row["id"] in seen:
            raise ValueError(f"Duplicate {name} id: {row['id']}")
        seen.add(row["id"])
    return value


def _simulate(vehicle, route, depot):
    load = sum(job["demand"] for job in route)
    if load > vehicle["capacity"] + 1e-9:
        return None, "capacity"
    clock, distance, position = vehicle["shift_start"], 0.0, depot
    stops = []
    for job in route:
        leg = math.dist(position, job["location"])
        arrival = clock + leg / vehicle["speed"]
        start = max(arrival, job["window_start"])
        finish = start + job["service_minutes"]
        if finish > job["window_end"] + 1e-9:
            return None, "service_completion_window"
        if finish > vehicle["shift_end"] + 1e-9:
            return None, "shift_end"
        stops.append({"job": job["id"], "arrival_minute": round(arrival, 3), "service_start_minute": round(start, 3), "service_end_minute": round(finish, 3), "wait_minutes": round(start - arrival, 3), "demand": job["demand"], "location": job["location"], "leg_distance_units": round(leg, 3)})
        clock, position, distance = finish, job["location"], distance + leg
    home_leg = math.dist(position, depot)
    end = clock + home_leg / vehicle["speed"]
    if end > vehicle["shift_end"] + 1e-9:
        return None, "return_to_depot_after_shift"
    return {"vehicle": vehicle["id"], "load": load, "capacity": vehicle["capacity"], "distance_units": round(distance + home_leg, 3), "return_minute": round(end, 3), "stops": stops}, None


def _plan(vehicles, jobs, depot, insertion):
    routes = [[] for _ in vehicles]
    unassigned = []
    ordered = sorted(jobs, key=lambda j: (j["window_end"], math.dist(depot, j["location"]), j["id"])) if insertion else jobs
    for job in ordered:
        candidates, reasons = [], set()
        for index, vehicle in enumerate(vehicles):
            old, _ = _simulate(vehicle, routes[index], depot)
            positions = range(len(routes[index]) + 1) if insertion else [len(routes[index])]
            for position in positions:
                trial = routes[index][:position] + [job] + routes[index][position:]
                result, reason = _simulate(vehicle, trial, depot)
                if result:
                    candidates.append((result["distance_units"] - old["distance_units"], result["return_minute"], vehicle["id"], position, index, trial))
                else:
                    reasons.add(reason)
            if candidates and not insertion:
                break
        if candidates:
            best = min(candidates, key=lambda c: c[:4])
            routes[best[4]] = best[5]
        else:
            single_reasons = sorted({_simulate(v, [job], depot)[1] for v in vehicles if _simulate(v, [job], depot)[1] is not None})
            individually_feasible = any(_simulate(v, [job], depot)[0] is not None for v in vehicles)
            unassigned.append({"job": job["id"], "reason": "fleet_commitments_prevent_insertion" if individually_feasible else "no_individually_feasible_vehicle", "constraint_evidence": sorted(reasons), "single_job_constraint_evidence": single_reasons})
    summaries = [_simulate(v, route, depot)[0] for v, route in zip(vehicles, routes)]
    return summaries, unassigned


def run(payload):
    if not isinstance(payload, dict):
        raise ValueError("Input must be an object")
    depot = _point(payload.get("depot", [0, 0]), "depot")
    vehicles = []
    for row in _rows(payload.get("vehicles"), "vehicles", 20):
        start = _number(row.get("shift_start", 0), "shift_start")
        end = _number(row.get("shift_end"), "shift_end")
        if end < start:
            raise ValueError("shift_end must be at or after shift_start")
        vehicles.append({"id": row["id"], "capacity": _number(row.get("capacity"), "capacity", True), "shift_start": start, "shift_end": end, "speed": _number(row.get("speed_units_per_minute", 1), "speed_units_per_minute", True)})
    if not vehicles:
        raise ValueError("At least one vehicle is required")
    jobs = []
    for row in _rows(payload.get("jobs"), "jobs", 80):
        start = _number(row.get("window_start", 0), "window_start")
        end = _number(row.get("window_end"), "window_end")
        if end < start:
            raise ValueError("window_end must be at or after window_start")
        jobs.append({"id": row["id"], "location": _point(row.get("location"), "location"), "demand": _number(row.get("demand"), "demand", True), "window_start": start, "window_end": end, "service_minutes": _number(row.get("service_minutes", 0), "service_minutes")})
    routes, unassigned = _plan(vehicles, jobs, depot, True)
    baseline, baseline_unassigned = _plan(vehicles, jobs, depot, False)
    distance = round(sum(r["distance_units"] for r in routes), 3)
    baseline_distance = round(sum(r["distance_units"] for r in baseline), 3)
    assigned = len(jobs) - len(unassigned)
    records = [{"vehicle": route["vehicle"], "sequence": index + 1, **stop} for route in routes for index, stop in enumerate(route["stops"])]
    assigned_ids = {row["job"] for row in records}
    baseline_ids = {stop["job"] for route in baseline for stop in route["stops"]}
    return {
        "summary": f"Assigned {assigned}/{len(jobs)} deliveries across {sum(bool(r['stops']) for r in routes)} vehicles; {len(unassigned)} require dispatcher review.",
        "metrics": {"assigned_jobs": assigned, "unassigned_jobs": len(unassigned), "distance_units": distance, "baseline_assigned_jobs": len(jobs) - len(baseline_unassigned), "baseline_distance_units": baseline_distance},
        "records": records, "routes": routes, "unassigned": unassigned,
        "baseline": {"method": "input-order, first-feasible-vehicle append", "routes": baseline, "unassigned": baseline_unassigned},
        "comparison": {"assigned_job_delta": len(baseline_unassigned) - len(unassigned), "distance_delta_units": round(distance - baseline_distance, 3), "distance_comparable": assigned_ids == baseline_ids, "served_job_sets_match": assigned_ids == baseline_ids},
        "warnings": ["Synthetic planar coordinates: distance units are Euclidean, not road kilometres or traffic-aware travel times.", "Deadline-ordered cheapest feasible insertion is a heuristic; it does not prove optimality or outperform every baseline.", "Windows constrain service completion. Every route must return to the depot before its shift ends. Capacity is total outbound delivery load."],
    }
