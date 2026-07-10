"""Command-line interface for the offline file agent.

Usage examples
--------------
    # Analyze a directory and print a report
    python -m offline_agent analyze ~/Downloads

    # Emit the analysis as JSON
    python -m offline_agent analyze ~/Downloads --json

    # Write a starter rules file
    python -m offline_agent init-rules rules.json

    # Preview automations (dry-run is the default)
    python -m offline_agent run ~/Downloads --rules rules.json

    # Actually apply the automations
    python -m offline_agent run ~/Downloads --rules rules.json --apply
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from typing import Optional

from .analyzer import analyze, scan
from .automation import AutomationEngine
from .report import render_analysis
from .rules import load_rules

EXAMPLE_RULES = [
    {
        "name": "Sort images into ./sorted/images",
        "match": {"category": "image"},
        "actions": [{"type": "move", "dest": "./sorted/images"}],
    },
    {
        "name": "Sort documents by year",
        "match": {"category": "document"},
        "actions": [{"type": "move", "dest": "./sorted/documents/{year}"}],
    },
    {
        "name": "Flag very large files (>500MB)",
        "match": {"min_size": "500MB"},
        "actions": [{"type": "log", "message": "large file: {name} ({size} bytes)"}],
    },
    {
        "name": "Archive old logs (>30 days)",
        "match": {"ext": ".log", "older_than_days": 30},
        "actions": [{"type": "move", "dest": "./archive/logs"}],
    },
]


def _add_scan_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("root", help="directory to scan")
    p.add_argument("--no-recursive", action="store_true",
                   help="do not descend into subdirectories")
    p.add_argument("--hidden", action="store_true",
                   help="include hidden files and directories")
    p.add_argument("--follow-symlinks", action="store_true",
                   help="follow symlinked directories")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                   help="glob pattern to exclude (repeatable)")


def _scan_files(args: argparse.Namespace):
    return scan(
        args.root,
        recursive=not args.no_recursive,
        include_hidden=args.hidden,
        follow_symlinks=args.follow_symlinks,
        exclude=args.exclude,
    )


def cmd_analyze(args: argparse.Namespace) -> int:
    files = list(_scan_files(args))
    analysis = analyze(files, top_n=args.top, find_duplicates=not args.no_duplicates)
    if args.json:
        print(json.dumps(_analysis_to_dict(analysis), indent=2))
    else:
        print(render_analysis(analysis, root=args.root))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        rules = load_rules(args.rules)
    except FileNotFoundError:
        print(f"Rules file not found: {args.rules}", file=sys.stderr)
        return 2
    if not rules:
        print("No rules loaded.", file=sys.stderr)
        return 2

    files = list(_scan_files(args))
    engine = AutomationEngine(rules, dry_run=not args.apply, base_dir=args.root)
    results = engine.run(files)

    for res in results:
        print(res)

    acted = sum(1 for r in results if r.ok)
    mode = "applied" if args.apply else "planned (dry-run)"
    print(f"\n{acted} action(s) {mode} across {len(files)} file(s).")
    if not args.apply and results:
        print("Re-run with --apply to execute these actions.")
    return 0


def cmd_init_rules(args: argparse.Namespace) -> int:
    import os

    if os.path.exists(args.path) and not args.force:
        print(f"Refusing to overwrite existing file: {args.path} "
              f"(use --force)", file=sys.stderr)
        return 2
    with open(args.path, "w", encoding="utf-8") as fh:
        json.dump({"rules": EXAMPLE_RULES}, fh, indent=2)
    print(f"Wrote starter rules to {args.path}")
    return 0


def _analysis_to_dict(analysis) -> dict:
    def fi_brief(fi):
        return {"path": fi.path, "size": fi.size,
                "modified": fi.modified_dt.isoformat()}

    return {
        "total_files": analysis.total_files,
        "total_size": analysis.total_size,
        "by_category": analysis.by_category,
        "size_by_category": analysis.size_by_category,
        "by_extension": analysis.by_extension,
        "largest": [fi_brief(f) for f in analysis.largest],
        "oldest": [fi_brief(f) for f in analysis.oldest],
        "duplicates": analysis.duplicates,
        "wasted_by_duplicates": analysis.wasted_by_duplicates,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="offline_agent",
        description="Offline file analysis and automation agent.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="analyze files and print a report")
    _add_scan_args(p_analyze)
    p_analyze.add_argument("--json", action="store_true", help="output JSON")
    p_analyze.add_argument("--top", type=int, default=10,
                           help="how many largest/oldest files to show")
    p_analyze.add_argument("--no-duplicates", action="store_true",
                           help="skip duplicate detection")
    p_analyze.set_defaults(func=cmd_analyze)

    p_run = sub.add_parser("run", help="run automations from a rules file")
    _add_scan_args(p_run)
    p_run.add_argument("--rules", required=True, help="path to a JSON rules file")
    p_run.add_argument("--apply", action="store_true",
                       help="actually perform actions (default is dry-run)")
    p_run.set_defaults(func=cmd_run)

    p_init = sub.add_parser("init-rules", help="write a starter rules file")
    p_init.add_argument("path", nargs="?", default="rules.json",
                        help="output path (default: rules.json)")
    p_init.add_argument("--force", action="store_true",
                        help="overwrite an existing file")
    p_init.set_defaults(func=cmd_init_rules)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
