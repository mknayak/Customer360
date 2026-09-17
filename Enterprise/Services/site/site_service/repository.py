from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock

from .models import Site, Visit

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "site.sqlite3"


class SiteRepository:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        with self.connection:
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sites (
                    site_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    city TEXT,
                    country TEXT,
                    opened_date TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS visits (
                    visit_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    site_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    FOREIGN KEY(site_id) REFERENCES sites(site_id)
                );
                """
            )

    @staticmethod
    def site(row: sqlite3.Row) -> Site:
        return Site(**dict(row))

    @staticmethod
    def visit(row: sqlite3.Row) -> Visit:
        return Visit(
            visit_id=row["visit_id"],
            customer_id=row["customer_id"],
            site_id=row["site_id"],
            channel=row["channel"],
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=(datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None),
        )

    def save_site(self, item: Site) -> Site:
        with self.lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO sites (
                    site_id, name, type, city, country, opened_date, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(site_id) DO UPDATE SET
                    name = excluded.name,
                    type = excluded.type,
                    city = excluded.city,
                    country = excluded.country,
                    opened_date = excluded.opened_date,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    item.site_id,
                    item.name,
                    item.type,
                    item.city,
                    item.country,
                    item.opened_date.isoformat() if item.opened_date else None,
                    item.status,
                    item.created_at.isoformat(),
                    item.updated_at.isoformat(),
                ),
            )
        return item

    def get_site(self, site_id: str) -> Site | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM sites WHERE site_id = ?", (site_id,)).fetchone()
        return self.site(row) if row else None

    def list_sites(self) -> list[Site]:
        with self.lock:
            rows = self.connection.execute("SELECT * FROM sites ORDER BY created_at, site_id").fetchall()
        return [self.site(row) for row in rows]

    def delete_site(self, site_id: str) -> None:
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM sites WHERE site_id = ?", (site_id,))

    def save_visit(self, item: Visit) -> Visit:
        with self.lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO visits (
                    visit_id, customer_id, site_id, channel, started_at, ended_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(visit_id) DO UPDATE SET
                    customer_id = excluded.customer_id,
                    site_id = excluded.site_id,
                    channel = excluded.channel,
                    started_at = excluded.started_at,
                    ended_at = excluded.ended_at
                """,
                (
                    item.visit_id,
                    item.customer_id,
                    item.site_id,
                    item.channel,
                    item.started_at.isoformat(),
                    item.ended_at.isoformat() if item.ended_at else None,
                ),
            )
        return item

    def get_visit(self, visit_id: str) -> Visit | None:
        with self.lock:
            row = self.connection.execute("SELECT * FROM visits WHERE visit_id = ?", (visit_id,)).fetchone()
        return self.visit(row) if row else None

    def list_visits(self, customer_id: str | None = None, site_id: str | None = None) -> list[Visit]:
        query = "SELECT * FROM visits"
        params: list[str] = []
        clauses: list[str] = []
        if customer_id:
            clauses.append("customer_id = ?")
            params.append(customer_id)
        if site_id:
            clauses.append("site_id = ?")
            params.append(site_id)
        if clauses:
            query = f"{query} WHERE {' AND '.join(clauses)}"
        query += " ORDER BY started_at DESC"
        with self.lock:
            rows = self.connection.execute(query, params).fetchall()
        return [self.visit(row) for row in rows]

    def close(self) -> None:
        with self.lock:
            self.connection.close()
