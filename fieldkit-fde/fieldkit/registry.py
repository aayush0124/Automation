"""Explicit tool allowlist, bounded inputs, and reproducible execution metadata."""
from copy import deepcopy
from hashlib import sha256
from importlib import import_module
import json
import math
from time import perf_counter
from uuid import uuid4

PROJECT_IDS = ("dockyard", "proofdesk", "evalforge", "ledgerguard", "relay",
               "switchboard", "routecraft", "consentline", "shiftforge", "launchgate")
MAX_BYTES = 1_048_576


def get_project(project_id):
    if project_id not in PROJECT_IDS:
        raise ValueError("Unknown project")
    return import_module("fieldkit.projects." + project_id)


def list_projects():
    return [deepcopy(get_project(key).SPEC) for key in PROJECT_IDS]


def validate_json(value, depth=0):
    if depth > 24:
        raise ValueError("Input exceeds 24 nesting levels")
    if isinstance(value, dict):
        if len(value) > 500 or any(not isinstance(k, str) for k in value):
            raise ValueError("Objects require string keys and at most 500 fields")
        for item in value.values():
            validate_json(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 500:
            raise ValueError("Arrays are limited to 500 items in this local demo")
        for item in value:
            validate_json(item, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite numbers are not accepted")
    elif value is not None and not isinstance(value, (str, bool, int, float)):
        raise ValueError("Only JSON values are accepted")


def parse_json(text):
    def reject_constant(_):
        raise ValueError("Non-finite JSON numbers are not accepted")
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON object keys are not accepted")
            result[key] = value
        return result
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Request exceeds 1 MiB")
    try:
        value = json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_keys)
    except (RecursionError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON") from exc
    validate_json(value)
    return value


def execute(project_id, payload):
    module = get_project(project_id)
    if not isinstance(payload, dict):
        raise ValueError("Project input must be a JSON object")
    validate_json(payload)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(canonical.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Request exceeds 1 MiB")
    started = perf_counter()
    result = module.run(deepcopy(payload))
    # Engines must return finite, serializable evidence, never an arbitrary object.
    json.dumps(result, allow_nan=False)
    return {"run_id": str(uuid4()), "project_id": project_id, "result": result,
            "elapsed_ms": round((perf_counter() - started) * 1000, 3),
            "input_sha256": sha256(canonical.encode()).hexdigest()}
