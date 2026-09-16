"""Apply service-owned SQLite schema migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path


MIGRATIONS_PATH = Path(__file__).resolve().parents[1] / "migrations"


def apply_migrations(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    applied = {
        row[0]
        for row in connection.execute(
            "SELECT migration_name FROM schema_migrations"
        )
    }

    for migration_path in sorted(MIGRATIONS_PATH.glob("*.sql")):
        if migration_path.name in applied:
            continue
        connection.executescript(migration_path.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO schema_migrations (migration_name) VALUES (?)",
            (migration_path.name,),
        )
    connection.commit()


def migrate_database(database_path: str | Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        apply_migrations(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    from .repository import DEFAULT_DATABASE_PATH

    migrate_database(DEFAULT_DATABASE_PATH)
