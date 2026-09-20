"""Typed contracts shared by the DecisionOS runtime components."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InvestigationStatus(StrEnum):
    CREATED = "created"
    PLANNED = "planned"
    RUNNING = "running"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    principal_id: str
    resource: str
    reason: str


@dataclass(frozen=True)
class ToolRequest:
    tool_name: str
    principal_id: str
    input: Mapping[str, Any]
    request_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class ToolResult:
    status: str
    data: Any = None
    source: tuple[str, ...] = ()
    definition: tuple[str, ...] = ()
    filters: Mapping[str, Any] = field(default_factory=dict)
    freshness: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    request_id: str = ""
    generated_at: datetime = field(default_factory=utc_now)
    query_metadata: Mapping[str, Any] = field(default_factory=dict)
    evidence_references: tuple[str, ...] = ()


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    claim: str
    source: str
    definition_version: str | None = None
    query_reference: str | None = None
    freshness: str | None = None
    synthetic: bool = False


@dataclass
class Investigation:
    question: str
    principal_id: str
    investigation_id: str = field(default_factory=lambda: str(uuid4()))
    status: InvestigationStatus = InvestigationStatus.CREATED
    plan: Mapping[str, Any] = field(default_factory=dict)
    tool_results: list[ToolResult] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def transition(self, next_status: InvestigationStatus) -> None:
        transitions = {
            InvestigationStatus.CREATED: {InvestigationStatus.PLANNED, InvestigationStatus.FAILED},
            InvestigationStatus.PLANNED: {InvestigationStatus.RUNNING, InvestigationStatus.FAILED},
            InvestigationStatus.RUNNING: {InvestigationStatus.VALIDATING, InvestigationStatus.FAILED},
            InvestigationStatus.VALIDATING: {InvestigationStatus.COMPLETED, InvestigationStatus.FAILED},
            InvestigationStatus.COMPLETED: set(),
            InvestigationStatus.FAILED: set(),
        }
        if next_status not in transitions[self.status]:
            raise ValueError(f"Invalid investigation transition: {self.status} -> {next_status}")
        self.status = next_status
        self.updated_at = utc_now()


@dataclass(frozen=True)
class DecisionBrief:
    investigation_id: str
    answer: str
    facts: tuple[str, ...]
    hypotheses: tuple[str, ...]
    recommendations: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    confidence: str
    limitations: tuple[str, ...] = ()
