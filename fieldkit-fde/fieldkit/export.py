"""Static artifacts come from executing the actual synthetic fixtures."""
import json
from pathlib import Path
from .registry import PROJECT_IDS, execute, get_project, list_projects


def export(destination=None):
    root = Path(destination) if destination else Path(__file__).resolve().parent.parent / "web"
    examples = root / "examples"
    examples.mkdir(parents=True, exist_ok=True)
    def write(path, data):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    write(root / "catalog.json", {"projects": list_projects(), "mode": "recorded-fixture-replay", "synthetic_data": True})
    for project_id in PROJECT_IDS:
        module = get_project(project_id)
        execution = execute(project_id, module.SAMPLE)
        write(examples / (project_id + ".json"), {"project": module.SPEC, "sample": module.SAMPLE,
              "result": execution["result"], "input_sha256": execution["input_sha256"],
              "mode": "recorded-fixture-replay", "synthetic_data": True})
    print(f"Exported {len(PROJECT_IDS)} executed fixture records to {root}")
