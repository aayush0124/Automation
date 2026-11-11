import argparse
import json
from pathlib import Path
import sys

from .registry import PROJECT_IDS, execute, get_project, list_projects, parse_json


def main():
    parser = argparse.ArgumentParser(description="Fieldkit FDE workflow lab — synthetic data, real computation")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List ten projects")
    sample = sub.add_parser("sample", help="Print a synthetic sample input")
    sample.add_argument("project", choices=PROJECT_IDS)
    run = sub.add_parser("run", help="Execute a sample or a supplied JSON input")
    run.add_argument("project", choices=PROJECT_IDS)
    run.add_argument("--input", type=Path)
    serve = sub.add_parser("serve", help="Serve loopback-only interactive lab")
    serve.add_argument("--port", type=int, default=8787)
    sub.add_parser("export", help="Generate static recorded fixture evidence")
    args = parser.parse_args()
    try:
        if args.command == "list":
            print(json.dumps(list_projects(), indent=2))
        elif args.command == "sample":
            print(json.dumps(get_project(args.project).SAMPLE, indent=2, ensure_ascii=False))
        elif args.command == "run":
            payload = parse_json(args.input.read_text(encoding="utf-8")) if args.input else get_project(args.project).SAMPLE
            print(json.dumps(execute(args.project, payload), indent=2, ensure_ascii=False))
        elif args.command == "export":
            from .export import export
            export()
        else:
            from .server import create_server
            server = create_server(args.port)
            print(f"Fieldkit local lab: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
