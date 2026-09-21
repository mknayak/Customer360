"""Reusable bounded investigation plans for executive workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .model_provider import ModelProvider, bounded_request
from .semantic import SemanticRegistry
from .workflow import WorkflowOrchestrator, WorkflowStep


@dataclass(frozen=True)
class InvestigationPlan:
    question: str
    metric_term: str
    tools: tuple[str, ...]
    stages: tuple[str, ...]


class BoundedInvestigator:
    def __init__(self, semantic: SemanticRegistry, model: ModelProvider, workflows: WorkflowOrchestrator) -> None:
        self.semantic = semantic
        self.model = model
        self.workflows = workflows

    def plan(self, question: str, metric_term: str) -> InvestigationPlan:
        lookup = self.semantic.lookup(metric_term)
        if lookup.status != "resolved":
            raise ValueError(f"Metric must resolve before investigation: {lookup.status}")
        response = self.model.complete(bounded_request(question, ("semantic.lookup", "analytics.query", "graph.search", "rag.search"), (lookup.definitions[0].definition,)))
        return InvestigationPlan(question, metric_term, ("semantic.lookup", "analytics.query", "graph.search", "rag.search"), ("permission-check", "semantic-lookup", "analytics-query", "evidence-validation", response.text))

    def run(self, investigation_id: str, plan: InvestigationPlan, actions: Mapping[str, Any]) -> Any:
        steps = []
        for stage in plan.stages[:4]:
            action = actions.get(stage)
            if not callable(action):
                continue
            steps.append(WorkflowStep(stage, action, retry_limit=1, timeout_seconds=5))
        if not steps:
            raise ValueError("Investigation requires at least one governed action")
        return self.workflows.run(investigation_id, steps, idempotency_key=f"{investigation_id}:{plan.metric_term}")
