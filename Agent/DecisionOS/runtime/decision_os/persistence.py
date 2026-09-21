"""Persistence ports and a deterministic in-memory adapter for the MVP."""

from __future__ import annotations

import pickle
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Mapping, Protocol

from .models import DecisionBrief, Evidence, Investigation
from .workflow import WorkflowRecord, WorkflowPersistence


class Persistence(WorkflowPersistence, Protocol):
    def save_investigation(self, investigation: Investigation) -> None: ...

    def get_investigation(self, investigation_id: str) -> Investigation: ...

    def save_decision(self, decision: DecisionBrief) -> None: ...

    def get_decision(self, investigation_id: str) -> DecisionBrief: ...


class InMemoryPersistence:
    """Replaceable adapter used until the PostgreSQL persistence layer exists."""

    def __init__(self) -> None:
        self._investigations: dict[str, Investigation] = {}
        self._decisions: dict[str, DecisionBrief] = {}
        self._workflows: dict[str, WorkflowRecord] = {}

    def save_investigation(self, investigation: Investigation) -> None:
        self._investigations[investigation.investigation_id] = replace(
            investigation,
            plan=dict(investigation.plan),
            tool_results=list(investigation.tool_results),
            evidence=list(investigation.evidence),
        )

    def get_investigation(self, investigation_id: str) -> Investigation:
        try:
            investigation = self._investigations[investigation_id]
        except KeyError as error:
            raise KeyError(f"Unknown investigation: {investigation_id}") from error
        return replace(
            investigation,
            plan=dict(investigation.plan),
            tool_results=list(investigation.tool_results),
            evidence=list(investigation.evidence),
        )

    def save_decision(self, decision: DecisionBrief) -> None:
        self._decisions[decision.investigation_id] = decision

    def get_decision(self, investigation_id: str) -> DecisionBrief:
        try:
            return self._decisions[investigation_id]
        except KeyError as error:
            raise KeyError(f"Unknown decision for investigation: {investigation_id}") from error

    def save_workflow(self, workflow: WorkflowRecord) -> None:
        self._workflows[workflow.workflow_id] = replace(
            workflow,
            steps=list(workflow.steps),
            audit_events=list(workflow.audit_events),
            evidence_references=list(workflow.evidence_references),
        )

    def get_workflow(self, workflow_id: str) -> WorkflowRecord:
        try:
            workflow = self._workflows[workflow_id]
        except KeyError as error:
            raise KeyError(f"Unknown workflow: {workflow_id}") from error
        return replace(
            workflow,
            steps=list(workflow.steps),
            audit_events=list(workflow.audit_events),
            evidence_references=list(workflow.evidence_references),
        )

    def get_workflow_by_idempotency(self, idempotency_key: str) -> WorkflowRecord | None:
        for workflow in self._workflows.values():
            if workflow.idempotency_key == idempotency_key:
                return self.get_workflow(workflow.workflow_id)
        return None


class SQLitePersistence:
    """Durable local adapter for investigations, decisions, workflows, and audits."""

    def __init__(self, database_path: str | Path) -> None:
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        with self.connection:
            self.connection.execute("CREATE TABLE IF NOT EXISTS decision_records (record_type TEXT NOT NULL, record_id TEXT PRIMARY KEY, payload BLOB NOT NULL)")
            self.connection.execute("CREATE TABLE IF NOT EXISTS decision_audit (audit_id INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL, principal_id TEXT NOT NULL, action TEXT NOT NULL, created_at TEXT NOT NULL, metadata BLOB NOT NULL)")
            self.connection.execute("CREATE TABLE IF NOT EXISTS decision_memory (memory_id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, payload BLOB NOT NULL, expires_at TEXT, deleted_at TEXT)")

    def _save(self, record_type: str, record_id: str, value: object) -> None:
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO decision_records VALUES (?, ?, ?)", (record_type, record_id, pickle.dumps(value)))

    def _get(self, record_id: str):
        row = self.connection.execute("SELECT payload FROM decision_records WHERE record_id = ?", (record_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown durable record: {record_id}")
        return pickle.loads(row[0])

    def save_investigation(self, investigation: Investigation) -> None:
        self._save("investigation", investigation.investigation_id, investigation)

    def get_investigation(self, investigation_id: str) -> Investigation:
        return self._get(investigation_id)

    def save_decision(self, decision: DecisionBrief) -> None:
        self._save("decision", decision.investigation_id, decision)

    def get_decision(self, investigation_id: str) -> DecisionBrief:
        return self._get(investigation_id)

    def save_workflow(self, workflow: WorkflowRecord) -> None:
        self._save("workflow", workflow.workflow_id, workflow)

    def get_workflow(self, workflow_id: str) -> WorkflowRecord:
        return self._get(workflow_id)

    def get_workflow_by_idempotency(self, idempotency_key: str) -> WorkflowRecord | None:
        row = self.connection.execute("SELECT payload FROM decision_records WHERE record_type = 'workflow'").fetchall()
        for (payload,) in row:
            workflow = pickle.loads(payload)
            if workflow.idempotency_key == idempotency_key:
                return workflow
        return None

    def append_audit(self, record_id: str, principal_id: str, action: str, metadata: dict[str, object] | None = None) -> None:
        from datetime import datetime, timezone
        with self.connection:
            self.connection.execute("INSERT INTO decision_audit (record_id, principal_id, action, created_at, metadata) VALUES (?, ?, ?, ?, ?)", (record_id, principal_id, action, datetime.now(timezone.utc).isoformat(), pickle.dumps(metadata or {})))

    def audit(self, record_id: str) -> list[dict[str, object]]:
        return [{"record_id": row[0], "principal_id": row[1], "action": row[2], "created_at": row[3], "metadata": pickle.loads(row[4])} for row in self.connection.execute("SELECT record_id, principal_id, action, created_at, metadata FROM decision_audit WHERE record_id = ? ORDER BY audit_id", (record_id,))]

    def save_evidence(self, evidence: Evidence) -> None:
        self._save("evidence", evidence.evidence_id, evidence)

    def get_evidence(self, evidence_id: str) -> Evidence:
        return self._get(evidence_id)

    def save_memory(self, memory_id: str, principal_id: str, payload: Mapping[str, object], expires_at: str | None = None) -> None:
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO decision_memory VALUES (?, ?, ?, ?, NULL)", (memory_id, principal_id, pickle.dumps(dict(payload)), expires_at))

    def purge_expired_memory(self, now: str) -> int:
        with self.connection:
            cursor = self.connection.execute("UPDATE decision_memory SET deleted_at = ? WHERE expires_at IS NOT NULL AND expires_at <= ? AND deleted_at IS NULL", (now, now))
            return cursor.rowcount

    def close(self) -> None:
        self.connection.close()
