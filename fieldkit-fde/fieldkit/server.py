"""Loopback-only development server. Not an Internet-facing deployment server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlsplit, unquote

from .audit import AuditStore
from .registry import MAX_BYTES, execute, get_project, list_projects, parse_json

ROOT = Path(__file__).resolve().parent.parent


class FieldkitHandler(BaseHTTPRequestHandler):
    server_version = "FieldkitLocal/0.1"
    timeout = 10

    def log_message(self, *_):
        pass  # Do not persist request paths or supplied values.

    def send(self, status, content, mime="application/json; charset=utf-8"):
        data = content if isinstance(content, bytes) else json.dumps(content, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def valid_origin(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            self.send(403, {"error": "Only this loopback host is accepted"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in hosts}:
            self.send(403, {"error": "Cross-origin requests are not accepted"})
            return False
        return True

    def do_GET(self):
        if not self.valid_origin():
            return
        path = urlsplit(self.path).path
        if path == "/api/health":
            return self.send(200, {"status": "ok", "mode": "local-demo", "synthetic_data": True})
        if path == "/api/projects":
            return self.send(200, {"projects": list_projects()})
        if path == "/api/runs":
            return self.send(200, {"runs": self.server.audit.recent()})
        if path.startswith("/api/projects/"):
            try:
                project = get_project(path.removeprefix("/api/projects/"))
                return self.send(200, {"project": project.SPEC, "sample": project.SAMPLE})
            except ValueError:
                return self.send(404, {"error": "Unknown project"})
        if path.startswith("/api/"):
            return self.send(404, {"error": "Unknown endpoint"})
        web = (ROOT / "web").resolve()
        try:
            decoded = unquote(path)
            if "\x00" in decoded or "\\" in decoded:
                return self.send(404, {"error": "Not found"})
            asset = (web / decoded.lstrip("/")).resolve() if path != "/" else web / "index.html"
            allowed = asset.is_relative_to(web) and asset.is_file() and asset.suffix in {".html", ".js", ".css", ".json", ".svg"}
        except (ValueError, OSError):
            allowed = False
        if not allowed:
            return self.send(404, {"error": "Not found"})
        mime = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
        if asset.suffix == ".js":
            mime = "text/javascript"
        return self.send(200, asset.read_bytes(), mime + "; charset=utf-8")

    def do_POST(self):
        if not self.valid_origin():
            return
        path = urlsplit(self.path).path
        if not path.startswith("/api/run/"):
            return self.send(404, {"error": "Unknown endpoint"})
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self.send(415, {"error": "Use Content-Type: application/json"})
        try:
            if self.headers.get("Transfer-Encoding"):
                return self.send(400, {"error": "Chunked requests are not accepted"})
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BYTES:
                return self.send(413, {"error": "Request must be between 1 byte and 1 MiB"})
            payload = parse_json(self.rfile.read(size).decode("utf-8"))
            run = execute(path.removeprefix("/api/run/"), payload)
            self.server.audit.append(run)
            return self.send(200, run)
        except (ValueError, UnicodeDecodeError) as exc:
            return self.send(400, {"error": str(exc)[:300]})
        except Exception:
            return self.send(500, {"error": "Workflow failed unexpectedly; no external action was taken"})


def create_server(port=8787, audit_path=None):
    if os.environ.get("FIELDKIT_ENV", "local") != "local":
        raise ValueError("Production serving is disabled. Add verified authentication and a production server first.")
    server = ThreadingHTTPServer(("127.0.0.1", port), FieldkitHandler)
    server.daemon_threads = True
    server.audit = AuditStore(audit_path or ROOT / ".local" / "audit.sqlite3")
    return server
