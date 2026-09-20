"""Durable, bounded workflow orchestration for DecisionOS investigations."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol
from uuid import uuid4

from .models import ToolResult

WorkflowAction = Callable[[], Any]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    action: WorkflowAction
    compensation: WorkflowAction | None = None
    retry_limit: int = 0
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Workflow step name cannot be empty")
        if self.retry_limit < 0:
            raise ValueError("Workflow retry limit cannot be negative")
        if self.timeout_seconds <= 0:
            raise ValueError("Workflow timeout must be greater than zero")


@dataclass(frozen=True)
class WorkflowStepRecord:
    name: str
    status: str
    attempts: int = 0
    result: Any = None
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


@dataclass
class WorkflowRecord:
    workflow_id: str
    investigation_id: str
    idempotency_key: str
    status: str = "created"
    current_step: str | None = None
    steps: list[WorkflowStepRecord] = field(default_factory=list)
    audit_events: list[str] = field(default_factory=list)
    evidence_references: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def summary(self) -> dict[str, Any]:
        completed = [step.name for step in self.steps if step.status == "completed"]
        failed = [step.name for step in self.steps if step.status == "failed"]
        return {
            "workflow_id": self.workflow_id,
            "investigation_id": self.investigation_id,
            "status": self.status,
            "completed_steps": tuple(completed),
            "failed_steps": tuple(failed),
            "omitted_steps": tuple(step.name for step in self.steps if step.status == "omitted"),
            "evidence_references": tuple(dict.fromkeys(self.evidence_references)),
            "audit_events": tuple(self.audit_events),
        }


class WorkflowPersistence(Protocol):
    def save_workflow(self, workflow: WorkflowRecord) -> None: ...

    def get_workflow(self, workflow_id: str) -> WorkflowRecord: ...

    def get_workflow_by_idempotency(self, idempotency_key: str) -> WorkflowRecord | None: ...


class WorkflowOrchestrator:
    """Execute ordered workflow steps with explicit failure semantics."""

    def __init__(self, persistence: WorkflowPersistence) -> None:
        self._persistence = persistence

    def run(
        self,
        investigation_id: str,
        steps: Iterable[WorkflowStep],
        idempotency_key: str | None = None,
    ) -> WorkflowRecord:
        ordered_steps = tuple(steps)
        if not ordered_steps:
            raise ValueError("Workflow must contain at least one step")
        key = idempotency_key or f"{investigation_id}:{','.join(step.name for step in ordered_steps)}"
        existing = self._persistence.get_workflow_by_idempotency(key)
        if existing is not None:
            return existing
        workflow = WorkflowRecord(str(uuid4()), investigation_id, key, status="running")
        self._persistence.save_workflow(workflow)
        completed: list[tuple[WorkflowStep, WorkflowStepRecord]] = []
        try:
            for step in ordered_steps:
                workflow.current_step = step.name
                record = self._execute_step(step, workflow)
                workflow.steps.append(record)
                workflow.updated_at = _now()
                self._persistence.save_workflow(workflow)
                if record.status != "completed":
                    workflow.status = "failed"
                    workflow.audit_events.append(f"workflow failed at step {step.name}: {record.error}")
                    self._compensate(workflow, completed)
                    workflow.current_step = None
                    workflow.updated_at = _now()
                    self._persistence.save_workflow(workflow)
                    return workflow
                completed.append((step, record))
                self._collect_evidence(workflow, record.result)
            workflow.status = "completed"
            workflow.audit_events.append("workflow completed")
        except Exception as error:
            workflow.status = "failed"
            workflow.audit_events.append(f"workflow orchestration error: {error}")
            self._compensate(workflow, completed)
        workflow.current_step = None
        workflow.updated_at = _now()
        self._persistence.save_workflow(workflow)
        return workflow

    def _execute_step(self, step: WorkflowStep, workflow: WorkflowRecord) -> WorkflowStepRecord:
        started_at = _now()
        last_error: str | None = None
        for attempt in range(1, step.retry_limit + 2):
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(step.action)
            try:
                result = future.result(timeout=step.timeout_seconds)
                if isinstance(result, ToolResult) and result.status not in {"succeeded"}:
                    raise RuntimeError(f"tool returned {result.status}")
                executor.shutdown(wait=False, cancel_futures=True)
                return WorkflowStepRecord(step.name, "completed", attempt, result, started_at=started_at, finished_at=_now())
            except FutureTimeoutError:
                last_error = f"timeout after {step.timeout_seconds}s"
                future.cancel()
            except Exception as error:
                last_error = str(error)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
            workflow.audit_events.append(f"step {step.name} attempt {attempt} failed: {last_error}")
        return WorkflowStepRecord(step.name, "failed", step.retry_limit + 1, error=last_error, started_at=started_at, finished_at=_now())

    def _compensate(self, workflow: WorkflowRecord, completed: list[tuple[WorkflowStep, WorkflowStepRecord]]) -> None:
        for step, _record in reversed(completed):
            if step.compensation is None:
                workflow.audit_events.append(f"step {step.name} has no compensation")
                continue
            try:
                step.compensation()
                workflow.audit_events.append(f"compensated step {step.name}")
            except Exception as error:
                workflow.audit_events.append(f"compensation failed for step {step.name}: {error}")

    @staticmethod
    def _collect_evidence(workflow: WorkflowRecord, result: Any) -> None:
        if isinstance(result, ToolResult):
            workflow.evidence_references.extend(result.evidence_references)
        elif isinstance(result, Mapping):
            references = result.get("evidence_references", ())
            if isinstance(references, (list, tuple)):
                workflow.evidence_references.extend(str(reference) for reference in references)