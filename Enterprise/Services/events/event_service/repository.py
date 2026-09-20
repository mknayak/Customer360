from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock

from .models import Event

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "events.sqlite3"


class EventRepository:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        with self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    source_service TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    correlation_id TEXT,
                    causation_id TEXT,
                    idempotency_key TEXT,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(events)")}
            if "idempotency_key" not in columns:
                self.connection.execute("ALTER TABLE events ADD COLUMN idempotency_key TEXT")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id)")
            self.connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_idempotency ON events(idempotency_key) WHERE idempotency_key IS NOT NULL"
            )

    @staticmethod
    def event(row: sqlite3.Row) -> Event:
        return Event(
            event_id=row["event_id"],
            source_service=row["source_service"],
            event_type=row["event_type"],
            aggregate_type=row["aggregate_type"],
            aggregate_id=row["aggregate_id"],
            payload=json.loads(row["payload"]),
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
            correlation_id=row["correlation_id"],
            causation_id=row["causation_id"],
            idempotency_key=row["idempotency_key"],
            schema_version=row["schema_version"],
        )

    def append(self, item: Event) -> Event:
        with self.lock, self.connection:
            if item.idempotency_key:
                existing = self.connection.execute(
                    "SELECT * FROM events WHERE idempotency_key = ?",
                    (item.idempotency_key,),
                ).fetchone()
                if existing is not None:
                    return self.event(existing)
            self.connection.execute(
                """
                INSERT INTO events (
                    event_id, source_service, event_type, aggregate_type, aggregate_id,
                    payload, occurred_at, recorded_at, correlation_id, causation_id, idempotency_key, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.event_id,
                    item.source_service,
                    item.event_type,
                    item.aggregate_type,
                    item.aggregate_id,
                    json.dumps(item.payload, separators=(",", ":"), sort_keys=True),
                    item.occurred_at.isoformat(),
                    item.recorded_at.isoformat(),
                    item.correlation_id,
                    item.causation_id,
                    item.idempotency_key,
                    item.schema_version,
                ),
            )
        return item

    def list_events(
        self,
        event_type: str | None = None,
        source_service: str | None = None,
        correlation_id: str | None = None,
        recorded_after: datetime | None = None,
        limit: int = 100,
    ) -> list[Event]:
        clauses: list[str] = []
        params: list[str | int] = []
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if source_service:
            clauses.append("source_service = ?")
            params.append(source_service)
        if correlation_id:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)
        if recorded_after:
            clauses.append("recorded_at > ?")
            params.append(recorded_after.isoformat())
        query = "SELECT * FROM events"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY recorded_at, event_id LIMIT ?"
        params.append(limit)
        with self.lock:
            rows = self.connection.execute(query, params).fetchall()
        return [self.event(row) for row in rows]

    def close(self) -> None:
        with self.lock:
            self.connection.close()
