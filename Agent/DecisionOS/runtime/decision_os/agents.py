"""Bounded domain-agent contracts and deterministic orchestration helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .models import DecisionBrief


@dataclass(frozen=True)
class AgentSpec:
    name: str
    scope: str
    primary_prompt: str
    allowed_tools: tuple[str, ...]
    memory_boundary: str
    required_inputs: tuple[str, ...]
    escalation_rules: tuple[str, ...]
    failure_behavior: str
    keywords: tuple[str, ...] = ()
    write_access: str = "working memory only"


@dataclass(frozen=True)
class AgentTask:
    question: str
    principal_id: str
    investigation_id: str
    inputs: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentFinding:
    agent_name: str
    answer: str
    facts: tuple[str, ...] = ()
    interpretations: tuple[str, ...] = ()
    hypotheses: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    confidence: str = "low"
    limitations: tuple[str, ...] = ()


class AgentPack:
    """Registry and router for bounded Customer360 agent roles.

    The pack only plans and validates work. Governed tool results are supplied
    as task inputs, so an agent cannot reach an operational database directly.
    """

    def __init__(self, specs: tuple[AgentSpec, ...] | None = None) -> None:
        self._specs = {spec.name: spec for spec in specs or default_agent_specs()}

    def specs(self) -> tuple[AgentSpec, ...]:
        return tuple(self._specs.values())

    def get(self, name: str) -> AgentSpec:
        try:
            return self._specs[name]
        except KeyError as error:
            raise ValueError(f"Unknown DecisionOS agent: {name}") from error

    def route(self, question: str) -> tuple[str, ...]:
        normalized = question.casefold().strip()
        if not normalized:
            raise ValueError("Question cannot be empty")
        scores = {
            name: sum(1 for keyword in spec.keywords if keyword in normalized)
            for name, spec in self._specs.items()
            if name not in {"executive-orchestrator", "evidence-validator", "memory-steward"}
        }
        selected = tuple(name for name, score in scores.items() if score > 0)
        return selected or ("executive-orchestrator",)

    def plan(self, question: str, principal_id: str, investigation_id: str) -> Mapping[str, Any]:
        specialists = self.route(question)
        selected = specialists + (("evidence-validator",) if specialists != ("executive-orchestrator",) else ())
        return {
            "question": question,
            "principal_id": principal_id,
            "investigation_id": investigation_id,
            "agents": selected,
            "required_tools": tuple(
                tool for name in selected for tool in self.get(name).allowed_tools
            ),
            "validation": ("evidence references", "confidence", "unsupported causality"),
        }

    def validate_finding(self, finding: AgentFinding) -> AgentFinding:
        self.get(finding.agent_name)
        limitations = list(finding.limitations)
        confidence = finding.confidence
        if not finding.evidence_ids:
            confidence = "low"
            if "No evidence references supplied" not in limitations:
                limitations.append("No evidence references supplied")
        return AgentFinding(
            agent_name=finding.agent_name,
            answer=finding.answer,
            facts=finding.facts,
            interpretations=finding.interpretations,
            hypotheses=finding.hypotheses,
            recommendations=finding.recommendations,
            evidence_ids=finding.evidence_ids,
            confidence=confidence,
            limitations=tuple(limitations),
        )

    def decision_brief(self, investigation_id: str, findings: tuple[AgentFinding, ...]) -> DecisionBrief:
        validated = tuple(self.validate_finding(finding) for finding in findings)
        evidence_ids = tuple(dict.fromkeys(
            evidence_id for finding in validated for evidence_id in finding.evidence_ids
        ))
        limitations = tuple(dict.fromkeys(
            limitation for finding in validated for limitation in finding.limitations
        ))
        confidence = "high" if validated and all(item.confidence == "high" for item in validated) else "medium"
        if not evidence_ids:
            confidence = "low"
        return DecisionBrief(
            investigation_id=investigation_id,
            answer=" ".join(item.answer for item in validated) or "No bounded finding was produced.",
            facts=tuple(fact for item in validated for fact in item.facts),
            hypotheses=tuple(hypothesis for item in validated for hypothesis in item.hypotheses),
            recommendations=tuple(
                recommendation for item in validated for recommendation in item.recommendations
            ),
            evidence_ids=evidence_ids,
            confidence=confidence,
            limitations=limitations,
        )


def default_agent_specs() -> tuple[AgentSpec, ...]:
    common_read_tools = ("permission.check",)
    return (
        AgentSpec(
            "executive-orchestrator", "Plan and coordinate investigations", "prompts/executive-orchestrator.md",
            common_read_tools + ("semantic.lookup", "lineage.explain", "decision.record"),
            "scoped conversation and decision memory", ("question", "principal_id"),
            ("ambiguous metrics", "unauthorized data", "operational or financial action"),
            "Surface the blocker and stop delegation.", ("why", "investigate", "decision", "performance"),
            "approved decision record",
        ),
        AgentSpec(
            "customer-intelligence", "Retention, churn, segments, frequency, customer value", "prompts/customer-intelligence.md",
            common_read_tools + ("analytics.query", "graph.search", "rag.search"), "working memory only",
            ("question", "principal_id", "time_period"), ("missing customer identity", "unsupported churn causality"),
            "Return a limitation with no recommendation.", ("customer", "retention", "churn", "segment", "lifetime", "repeat"),
        ),
        AgentSpec("product-intelligence", "Product, category, price, demand, affinity", "prompts/product-intelligence.md", common_read_tools + ("analytics.query", "graph.search"), "working memory only", ("question", "principal_id", "time_period"), ("missing product definition", "inventory ambiguity"), "Return a limitation with no recommendation.", ("product", "category", "inventory", "demand", "price", "sell")),
        AgentSpec("promotion-intelligence", "Promotion effectiveness and economics", "prompts/promotion-intelligence.md", common_read_tools + ("analytics.query", "semantic.lookup"), "working memory only", ("question", "principal_id", "time_period"), ("missing comparison period", "correlation presented as uplift"), "Require a comparison or mark uplift unavailable.", ("promotion", "campaign", "uplift", "offer", "discount")),
        AgentSpec("digital-intelligence", "Visits, funnels, checkout, conversion", "prompts/digital-intelligence.md", common_read_tools + ("analytics.query", "graph.search"), "working memory only", ("question", "principal_id", "time_period"), ("stale site data", "missing funnel step"), "Return the incomplete funnel explicitly.", ("website", "site", "visit", "conversion", "funnel", "cart", "abandon")),
        AgentSpec("voice-of-customer", "Feedback themes, sentiment, complaints", "prompts/voice-of-customer.md", common_read_tools + ("analytics.query", "rag.search"), "working memory only", ("question", "principal_id", "time_period"), ("insufficient feedback", "sentiment uncertainty"), "Separate observed feedback from interpretation.", ("feedback", "complaint", "sentiment", "dissatisfaction", "review")),
        AgentSpec("finance-intelligence", "Revenue, margin, cost, variance, forecast", "prompts/finance-intelligence.md", common_read_tools + ("analytics.query", "semantic.lookup", "lineage.explain"), "working memory only", ("question", "principal_id", "time_period"), ("ambiguous revenue", "missing cost basis"), "Do not recommend financial action without validated definitions.", ("revenue", "margin", "finance", "cost", "profit", "forecast")),
        AgentSpec("evidence-validator", "Validate claims, sources, freshness, and causality", "prompts/decision-evaluator.md", common_read_tools + ("decision.evaluate", "lineage.explain"), "evaluation record", ("question", "evidence"), ("missing source", "stale evidence", "unsupported causality"), "Block completion and report the failed validation.", ("evidence", "validate", "confidence"), "evaluation record"),
        AgentSpec("memory-steward", "Govern memory retention, consent, and deletion", "memory/memory-policy.md", common_read_tools + ("memory.retrieve", "memory.store"), "authorized memory records", ("principal_id", "memory_policy"), ("missing consent", "retention violation"), "Fail closed and do not persist.", ("memory", "retain", "consent", "delete"), "memory records with policy approval"),
    )