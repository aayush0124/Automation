"""Run the suite and record measured evidence; no external network required."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-no-skips", action="store_true")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    from fieldkit.registry import PROJECT_IDS, execute, get_project
    records = []
    for project_id in PROJECT_IDS:
        project = get_project(project_id)
        run = execute(project_id, project.SAMPLE)
        second = execute(project_id, project.SAMPLE)
        stable = run["result"] == second["result"]
        if not stable:
            raise RuntimeError(f"Non-deterministic fixture: {project_id}")
        artifact = ROOT / "web" / "examples" / (project_id + ".json")
        if artifact.exists():
            exported = json.loads(artifact.read_text(encoding="utf-8"))
            if exported["result"] != run["result"] or exported["input_sha256"] != run["input_sha256"]:
                raise RuntimeError(f"Stale static export: {project_id}; run python -m fieldkit export")
        else:
            raise RuntimeError(f"Missing static export: {project_id}")
        records.append({"id": project_id, "input_sha256": run["input_sha256"], "deterministic": stable,
                        "metrics": run["result"]["metrics"], "static_export_matches": True})
    sources = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
               for folder in ("fieldkit", "tests", "web") for p in sorted((ROOT / folder).rglob("*"))
               if p.is_file() and p.suffix in {".py", ".js", ".css", ".html"}}
    evidence = {"verified_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
                "platform": platform.system(), "tests_run": result.testsRun,
                "failures": len(result.failures), "errors": len(result.errors),
                "skipped": [{"test": str(test), "reason": reason} for test, reason in result.skipped],
                "suite_success": result.wasSuccessful(), "projects": records, "source_sha256": sources,
                "source_hash_format": "UTF-8 with LF newlines, matching repository normalization",
                "scope": "Synthetic deterministic workflow and protocol verification; not customer outcomes or model evaluation",
                "browser_visual_review": "Not completed: browser control stopped during URL verification",
                "external_mcp_client_review": "Not completed; subprocess protocol tests are included"}
    destination = ROOT / "evidence" / "verification.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Evidence: {destination}")
    return 0 if result.wasSuccessful() and (not args.require_no_skips or not result.skipped) else 1


if __name__ == "__main__":
    raise SystemExit(main())
