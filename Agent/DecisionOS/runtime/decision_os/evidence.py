"""Evidence assembly and recommendation gating for DecisionOS decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .evaluation import DecisionEvaluator
from .models import DecisionBrief, Evidence, Investigation

_CAUSAL_MARKERS = ("because", "caused", "causes", "due to", "led to", "resulted in")


@dataclass(frozen=True)
class EvidenceValidation:
    passed: bool
    evidence: tuple[Evidence, ...]
    missing_evidence: tuple[str, ...] = ()
    denied_or_failed_sources: tuple[str, ...] = ()
    stale_evidence: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    unsupported_causal_claims: tuple[str, ...] = ()
    confidence: str = "low"
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionRecord:
    """Auditable output schema for a validated or blocked decision."""

    investigation_id: str
    question: str
    answer: str
    facts: tuple[str, ...]
    interpretations: tuple[str, ...]
    hypotheses: tuple[str, ...]
    key_drivers: tuple[str, ...]
    recommendations: tuple[str, ...]
    follow_up_questions: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    confidence: str
    limitations: tuple[str, ...] = ()
    status: str = "blocked"


class EvidencePipeline:
    """Assemble evidence from tool envelopes and gate unsafe recommendations."""

    def __init__(self, evaluator: DecisionEvaluator | None = None) -> None:
        self._evaluator = evaluator or DecisionEvaluator()

    def collect(self, investigation: Investigation) -> tuple[Evidence, ...]:
        collected: dict[str, Evidence] = {item.evidence_id: item for item in investigation.evidence}
        for result in investigation.tool_results:
            if result.status != "succeeded":
                continue
            for reference in result.evidence_references:
                collected.setdefault(
                    reference,
                    Evidence(
                        evidence_id=reference,
                        claim=f"Evidence returned by {result.query_metadata.get('tool', 'governed retrieval')}",
                        source=result.source[0] if result.source else "unknown",
                        query_reference=str(result.query_metadata.get("query_id", "")) or None,
                        freshness=str(result.freshness) if result.freshness else None,
                        synthetic=any("synthetic" in source.casefold() for source in result.source),
                    ),
                )
        return tuple(collected.values())

    def validate(
        self,
        investigation: Investigation,
        decision: DecisionBrief,
        required_claims: Iterable[str] = (),
    ) -> EvidenceValidation:
        evidence = self.collect(investigation)
        available = {item.evidence_id for item in evidence}
        missing_evidence = tuple(item for item in decision.evidence_ids if item not in available)
        denied_or_failed = tuple(
            source
            for result in investigation.tool_results
            if result.status != "succeeded"
            for source in (result.source or (result.status,))
        )
        stale = tuple(
            item.evidence_id
            for result in investigation.tool_results
            if result.status == "succeeded"
            and (result.freshness.get("stale") is True or result.freshness.get("superseded") is True or any("stale" in warning.casefold() or "superseded" in warning.casefold() for warning in result.warnings))
            for item in evidence
            if item.evidence_id in result.evidence_references
        )
        evaluated = self._evaluator.evaluate(decision, required_claims)
        causal_claims = tuple(
            hypothesis for hypothesis in decision.hypotheses
            if any(marker in hypothesis.casefold() for marker in _CAUSAL_MARKERS)
        )
        limitations = list(decision.limitations)
        if missing_evidence:
            limitations.append("Decision references evidence that was not returned by an authorized tool.")
        if denied_or_failed:
            limitations.append("One or more evidence sources were denied or failed.")
        if stale:
            limitations.append("Some evidence is stale or superseded.")
        if evaluated.missing_claims:
            limitations.append("Required claims are missing from the validated findings.")
        if evaluated.contradictions:
            limitations.append("Contradictory evidence prevents a supported conclusion.")
        if causal_claims:
            limitations.append("Causal hypotheses require explicit comparative evidence and are not recommendation-ready.")
        passed = bool(evidence) and not (
            missing_evidence or denied_or_failed or stale or evaluated.missing_claims or evaluated.contradictions or causal_claims
        )
        confidence = "high" if passed and evaluated.confidence == "high" else "medium" if evidence and evaluated.confidence != "low" else "low"
        return EvidenceValidation(
            passed=passed,
            evidence=evidence,
            missing_evidence=missing_evidence,
            denied_or_failed_sources=denied_or_failed,
            stale_evidence=stale,
            contradictions=evaluated.contradictions,
            unsupported_causal_claims=causal_claims,
            confidence=confidence,
            limitations=tuple(dict.fromkeys(limitations)),
        )

    def build_record(
        self,
        investigation: Investigation,
        decision: DecisionBrief,
        required_claims: Iterable[str] = (),
        key_drivers: Iterable[str] = (),
        follow_up_questions: Iterable[str] = (),
    ) -> DecisionRecord:
        validation = self.validate(investigation, decision, required_claims)
        recommendations = decision.recommendations if validation.passed else ()
        status = "validated" if validation.passed else "blocked"
        return DecisionRecord(
            investigation_id=decision.investigation_id,
            question=investigation.question,
            answer=decision.answer,
            facts=decision.facts,
            interpretations=(),
            hypotheses=decision.hypotheses,
            key_drivers=tuple(key_drivers),
            recommendations=recommendations,
            follow_up_questions=tuple(follow_up_questions),
            evidence=validation.evidence,
            confidence=validation.confidence,
            limitations=validation.limitations,
            status=status,
        )


def decision_record_tool_handler(pipeline: EvidencePipeline, investigations: Mapping[str, Investigation]):
    def handle(inputs: Mapping[str, Any]) -> DecisionRecord:
        investigation_id = inputs["investigation_id"]
        investigation = investigations[investigation_id]
        decision = inputs["decision_brief"]
        if not isinstance(decision, DecisionBrief):
            raise TypeError("decision_brief must be a DecisionBrief")
        return pipeline.build_record(
            investigation,
            decision,
            inputs.get("required_claims", ()),
            inputs.get("key_drivers", ()),
            inputs.get("follow_up_questions", ()),
        )

    return handle