"""Minimal local audit: retain metadata, never customer payloads or results."""
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
import sqlite3


class AuditStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                input_sha256 TEXT NOT NULL, elapsed_ms REAL NOT NULL,
                created_at TEXT NOT NULL)""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def append(self, run):
        with self.connect() as db:
            db.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?)",
                       (run["run_id"], run["project_id"], run["input_sha256"],
                        run["elapsed_ms"], datetime.now(timezone.utc).isoformat()))
            db.execute("DELETE FROM runs WHERE rowid NOT IN (SELECT rowid FROM runs ORDER BY rowid DESC LIMIT 1000)")

    def recent(self):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT * FROM runs ORDER BY rowid DESC LIMIT 30")]
