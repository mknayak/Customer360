"""Durable workflow state for orchestration requests."""

import json
import sqlite3
from pathlib import Path
from threading import RLock

from .models import WorkflowResult


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "orchestration.sqlite3"


class WorkflowRepository:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        with self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    workflow_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    result TEXT NOT NULL
                )
                """
            )
            self.connection.execute("CREATE INDEX IF NOT EXISTS idx_workflows_correlation ON workflows(correlation_id)")

    def save(self, workflow: WorkflowResult) -> WorkflowResult:
        with self.lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO workflows (workflow_id, workflow_type, status, correlation_id, result)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    status = excluded.status,
                    result = excluded.result
                """,
                (
                    workflow.workflow_id,
                    workflow.workflow_type,
                    workflow.status,
                    workflow.correlation_id,
                    json.dumps(workflow.model_dump(mode="json"), separators=(",", ":"), sort_keys=True),
                ),
            )
        return workflow

    def get(self, workflow_id: str) -> WorkflowResult | None:
        with self.lock:
            row = self.connection.execute("SELECT result FROM workflows WHERE workflow_id = ?", (workflow_id,)).fetchone()
        return WorkflowResult.model_validate(json.loads(row["result"])) if row else None

    def close(self) -> None:
        with self.lock:
            self.connection.close()