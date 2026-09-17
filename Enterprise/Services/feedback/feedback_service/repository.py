from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock

from .models import Feedback


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "feedback.sqlite3"


class FeedbackRepository:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        with self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    comment TEXT,
                    product_id TEXT,
                    order_id TEXT,
                    campaign_id TEXT,
                    site_id TEXT,
                    sentiment TEXT NOT NULL,
                    status TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column("campaign_id", "TEXT")

    def _ensure_column(self, column: str, definition: str) -> None:
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(feedback)")}
        if column not in columns:
            self.connection.execute(f"ALTER TABLE feedback ADD COLUMN {column} {definition}")

    @staticmethod
    def feedback(row: sqlite3.Row) -> Feedback:
        data = dict(row)
        data["submitted_at"] = datetime.fromisoformat(data["submitted_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return Feedback(**data)

    def save_feedback(self, item: Feedback) -> Feedback:
        with self.lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO feedback (
                    feedback_id, customer_id, source, rating, comment, product_id,
                    order_id, campaign_id, site_id, sentiment, status, submitted_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(feedback_id) DO UPDATE SET
                    customer_id = excluded.customer_id,
                    source = excluded.source,
                    rating = excluded.rating,
                    comment = excluded.comment,
                    product_id = excluded.product_id,
                    order_id = excluded.order_id,
                    campaign_id = excluded.campaign_id,
                    site_id = excluded.site_id,
                    sentiment = excluded.sentiment,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    item.feedback_id,
                    item.customer_id,
                    item.source,
                    item.rating,
                    item.comment,
                    item.product_id,
                    item.order_id,
                    item.campaign_id,
                    item.site_id,
                    item.sentiment,
                    item.status,
                    item.submitted_at.isoformat(),
                    item.updated_at.isoformat(),
                ),
            )
        return item

    def get_feedback(self, feedback_id: str) -> Feedback | None:
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM feedback WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        return self.feedback(row) if row else None

    def list_feedback(
        self,
        customer_id: str | None = None,
        source: str | None = None,
        status: str | None = None,
    ) -> list[Feedback]:
        clauses = []
        parameters: list[str] = []
        for column, value in (
            ("customer_id", customer_id),
            ("source", source),
            ("status", status),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.lock:
            rows = self.connection.execute(
                f"SELECT * FROM feedback {where} ORDER BY submitted_at, feedback_id",
                parameters,
            ).fetchall()
        return [self.feedback(row) for row in rows]

    def delete_feedback(self, feedback_id: str) -> None:
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM feedback WHERE feedback_id = ?", (feedback_id,))

    def close(self) -> None:
        self.connection.close()
