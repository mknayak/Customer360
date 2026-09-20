"""Persistence ports and a deterministic in-memory adapter for the MVP."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .models import DecisionBrief, Investigation
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
