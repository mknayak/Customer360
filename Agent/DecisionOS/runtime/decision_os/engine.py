"""Investigation lifecycle coordination."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .models import Investigation, InvestigationStatus, ToolRequest
from .persistence import Persistence
from .tools import ToolDispatcher


class InvestigationEngine:
    def __init__(self, persistence: Persistence, tools: ToolDispatcher) -> None:
        self._persistence = persistence
        self._tools = tools

    def create(self, question: str, principal_id: str) -> Investigation:
        if not question.strip():
            raise ValueError("Investigation question cannot be empty")
        investigation = Investigation(question=question, principal_id=principal_id)
        self._persistence.save_investigation(investigation)
        return investigation

    def plan(self, investigation_id: str, plan: Mapping[str, Any]) -> Investigation:
        investigation = self._load(investigation_id)
        investigation.transition(InvestigationStatus.PLANNED)
        investigation.plan = dict(plan)
        self._persistence.save_investigation(investigation)
        return investigation

    def run_tools(
        self,
        investigation_id: str,
        requests: Sequence[ToolRequest],
    ) -> Investigation:
        investigation = self._load(investigation_id)
        investigation.transition(InvestigationStatus.RUNNING)
        for request in requests:
            if request.principal_id != investigation.principal_id:
                raise PermissionError("Tool principal does not match investigation principal")
            investigation.tool_results.append(self._tools.dispatch(request))
        self._persistence.save_investigation(investigation)
        return investigation

    def begin_validation(self, investigation_id: str) -> Investigation:
        investigation = self._load(investigation_id)
        investigation.transition(InvestigationStatus.VALIDATING)
        self._persistence.save_investigation(investigation)
        return investigation

    def complete(self, investigation_id: str) -> Investigation:
        investigation = self._load(investigation_id)
        investigation.transition(InvestigationStatus.COMPLETED)
        self._persistence.save_investigation(investigation)
        return investigation

    def fail(self, investigation_id: str) -> Investigation:
        investigation = self._load(investigation_id)
        investigation.transition(InvestigationStatus.FAILED)
        self._persistence.save_investigation(investigation)
        return investigation

    def _load(self, investigation_id: str) -> Investigation:
        return self._persistence.get_investigation(investigation_id)
