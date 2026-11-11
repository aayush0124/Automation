"""Transactional webhook inbox/outbox laboratory. No external effects are sent."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from typing import Any

SPEC = {
    "id": "relay", "name": "Relay", "track": "reliability",
    "tagline": "Replay chaos. Deliver each local state transition once.",
    "description": "A durable webhook inbox/outbox with tenant-scoped deduplication, retries, dead letters and version ordering.",
    "customer": "A SaaS integration team receiving duplicate and out-of-order order webhooks.",
    "skills": ["SQLite transactions", "idempotency", "retry policies", "event ordering", "failure recovery"],
    "flagship": False,
}

SAMPLE = {
    "events": [
        {"tenant": "north", "key": "order-42-v2", "aggregate": "order-42", "version": 2, "body": {"state": "packed"}},
        {"tenant": "north", "key": "order-42-v1", "aggregate": "order-42", "version": 1, "body": {"state": "paid"}, "failures_before_success": 1},
        {"tenant": "north", "key": "order-42-v1", "aggregate": "order-42", "version": 1, "body": {"state": "paid"}},
        {"tenant": "south", "key": "order-42-v1", "aggregate": "order-42", "version": 1, "body": {"state": "paid"}},
        {"tenant": "north", "key": "order-43-v1", "aggregate": "order-43", "version": 1, "body": {"state": "paid"}, "failures_before_success": 99},
    ],
    "ticks": [0, 1, 2, 3, 7, 15], "max_attempts": 3, "base_delay_seconds": 1,
}


def _integer(value: Any, name: str, minimum: int = 0, maximum: int = 1000000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def _seconds(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value > 1e9:
        raise ValueError(f"{name} must be finite nonnegative seconds no greater than 1e9")
    return float(value)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(f"{name} must be a nonempty string up to 200 characters")
    return value


class RelayStore:
    """A single-consumer SQLite outbox; local state and delivery status commit atomically.

    The simulated sink is the aggregates table. This does not promise exactly-once
    delivery across an external network. A real sink must honor idempotency keys.
    """

    def __init__(self, path: str = ":memory:", *, max_attempts: int = 3,
                 base_delay_seconds: float = 1, max_order_waits: int = 5):
        self.max_attempts = _integer(max_attempts, "max_attempts", 1, 20)
        self.base_delay = _seconds(base_delay_seconds, "base_delay_seconds")
        if self.base_delay == 0:
            raise ValueError("base_delay_seconds must be positive")
        self.max_order_waits = _integer(max_order_waits, "max_order_waits", 1, 100)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS inbox (
                tenant TEXT NOT NULL, event_key TEXT NOT NULL, content_hash TEXT NOT NULL,
                aggregate_id TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL,
                PRIMARY KEY(tenant,event_key));
            CREATE TABLE IF NOT EXISTS outbox (
                tenant TEXT NOT NULL, event_key TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0, order_waits INTEGER NOT NULL DEFAULT 0,
                next_at REAL NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
                last_error TEXT, PRIMARY KEY(tenant,event_key),
                FOREIGN KEY(tenant,event_key) REFERENCES inbox(tenant,event_key));
            CREATE TABLE IF NOT EXISTS aggregates (
                tenant TEXT NOT NULL, aggregate_id TEXT NOT NULL, version INTEGER NOT NULL,
                body TEXT NOT NULL, PRIMARY KEY(tenant,aggregate_id));
        """)

    def close(self) -> None:
        self.db.close()

    def ingest(self, event: dict) -> dict:
        if not isinstance(event, dict):
            raise ValueError("each event must be an object")
        tenant = _text(event.get("tenant"), "tenant")
        key = _text(event.get("key"), "key")
        aggregate = _text(event.get("aggregate"), "aggregate")
        version = _integer(event.get("version"), "version", 1)
        body = event.get("body")
        if not isinstance(body, dict):
            raise ValueError("event body must be an object")
        try:
            body_json = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError("event body must contain finite JSON values") from exc
        if len(body_json) > 100000:
            raise ValueError("event body exceeds 100000 characters")
        digest = hashlib.sha256(json.dumps([aggregate, version, body_json], ensure_ascii=True).encode()).hexdigest()
        failures = _integer(event.get("failures_before_success", 0), "failures_before_success", 0, 100)
        with self.db:
            # Acquire the write lock before deduplication, including across processes.
            self.db.execute("BEGIN IMMEDIATE")
            existing = self.db.execute("SELECT content_hash FROM inbox WHERE tenant=? AND event_key=?", (tenant, key)).fetchone()
            if existing:
                return {"tenant": tenant, "key": key, "status": "duplicate" if existing[0] == digest else "conflict"}
            self.db.execute("INSERT INTO inbox VALUES(?,?,?,?,?,?)", (tenant, key, digest, aggregate, version, body_json))
            self.db.execute("INSERT INTO outbox(tenant,event_key,failures) VALUES(?,?,?)", (tenant, key, failures))
        return {"tenant": tenant, "key": key, "status": "accepted"}

    def process(self, now: float) -> list[dict]:
        now = _seconds(now, "now")
        trace = []
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            rows = self.db.execute("""SELECT i.*,o.status,o.attempts,o.order_waits,o.failures FROM inbox i
                JOIN outbox o USING(tenant,event_key) WHERE o.status IN ('pending','retry','waiting') AND o.next_at<=?
                ORDER BY i.tenant,i.aggregate_id,i.version,i.event_key""", (now,)).fetchall()
            for row in rows:
                identity = (row["tenant"], row["event_key"])
                state = self.db.execute("SELECT version FROM aggregates WHERE tenant=? AND aggregate_id=?", (row["tenant"], row["aggregate_id"])).fetchone()
                current = state[0] if state else 0
                attempts, waits, error, delay = row["attempts"], row["order_waits"], None, 0.0
                if row["version"] <= current:
                    status = "superseded"
                    error = "Version already applied or newer state exists"
                elif row["version"] != current + 1:
                    waits += 1
                    status = "dead_letter" if waits >= self.max_order_waits else "waiting"
                    delay = self.base_delay
                    error = f"Missing predecessor version {current + 1}"
                else:
                    attempts += 1
                    if attempts <= row["failures"]:
                        status = "dead_letter" if attempts >= self.max_attempts else "retry"
                        delay = min(self.base_delay * (2 ** (attempts - 1)), 60.0)
                        error = "Injected sink failure"
                    else:
                        status = "delivered"
                        self.db.execute("""INSERT INTO aggregates VALUES(?,?,?,?) ON CONFLICT(tenant,aggregate_id)
                            DO UPDATE SET version=excluded.version,body=excluded.body""",
                            (row["tenant"], row["aggregate_id"], row["version"], row["body"]))
                self.db.execute("UPDATE outbox SET status=?,attempts=?,order_waits=?,next_at=?,last_error=? WHERE tenant=? AND event_key=?",
                                (status, attempts, waits, now + delay, error, *identity))
                trace.append({"time_seconds": now, "tenant": identity[0], "key": identity[1], "version": row["version"],
                              "status": status, "attempts": attempts, "order_waits": waits,
                              "next_attempt_seconds": now + delay if status in ("retry", "waiting") else None, "reason": error})
        return trace

    def records(self) -> list[dict]:
        return [dict(row) for row in self.db.execute("""SELECT i.tenant,i.event_key AS key,i.aggregate_id AS aggregate,
            i.version,o.status,o.attempts,o.order_waits,o.next_at,o.last_error FROM inbox i JOIN outbox o
            USING(tenant,event_key) ORDER BY i.tenant,i.aggregate_id,i.version,i.event_key""")]

    def states(self) -> list[dict]:
        return [{"tenant": r["tenant"], "aggregate": r["aggregate_id"], "version": r["version"], "body": json.loads(r["body"])}
                for r in self.db.execute("SELECT * FROM aggregates ORDER BY tenant,aggregate_id")]


def run(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    events, ticks = payload.get("events"), payload.get("ticks", [0, 1, 2, 3, 7, 15])
    if not isinstance(events, list) or len(events) > 500:
        raise ValueError("events must be a list of at most 500 events")
    if not isinstance(ticks, list) or not 1 <= len(ticks) <= 100:
        raise ValueError("ticks must contain 1 to 100 simulation times")
    ticks = [_seconds(t, "tick") for t in ticks]
    if any(b <= a for a, b in zip(ticks, ticks[1:])):
        raise ValueError("ticks must be strictly increasing")
    store = RelayStore(max_attempts=payload.get("max_attempts", 3), base_delay_seconds=payload.get("base_delay_seconds", 1),
                       max_order_waits=payload.get("max_order_waits", 5))
    try:
        receipts = [store.ingest(event) for event in events]
        trace = [step for tick in ticks for step in store.process(tick)]
        records, states = store.records(), store.states()
    finally:
        store.close()
    counts = {s: sum(r["status"] == s for r in records) for s in ("delivered", "dead_letter", "superseded", "pending", "retry", "waiting")}
    duplicates = sum(r["status"] == "duplicate" for r in receipts)
    conflicts = sum(r["status"] == "conflict" for r in receipts)
    pending = sum(counts[s] for s in ("pending", "retry", "waiting"))
    warnings = ["Synthetic sink: no external webhook was sent. Exactly-once local state does not imply exactly-once network delivery."]
    if conflicts:
        warnings.append(f"{conflicts} idempotency-key conflicts rejected; existing payloads were preserved.")
    if pending:
        warnings.append(f"{pending} events remain pending at the end of the supplied simulation horizon.")
    return {"summary": f"{counts['delivered']} delivered, {duplicates} duplicates suppressed, {counts['dead_letter']} dead-lettered.",
            "metrics": {"received": len(events), "unique_events": len(records), "duplicates": duplicates, "conflicts": conflicts,
                        "delivered": counts["delivered"], "dead_letters": counts["dead_letter"], "pending": pending,
                        "delivery_attempts": sum(r["attempts"] for r in records)},
            "records": records, "warnings": warnings, "receipts": receipts, "trace": trace, "states": states,
            "data_mode": "synthetic deterministic simulation"}
