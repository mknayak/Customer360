"""Deterministic evaluation primitives for DecisionOS scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import DecisionBrief


@dataclass(frozen=True)
class EvaluationResult:
    passed: bool
    matched_claims: tuple[str, ...]
    missing_claims: tuple[str, ...]
    contradictions: tuple[str, ...]
    confidence: str


def _claim_forms(claim: str) -> set[str]:
    normalized = " ".join(claim.casefold().split())
    forms = {normalized}
    replacements = (
        ("did not ", ""),
        ("does not ", ""),
        ("is not ", "is "),
        ("not ", ""),
        ("increased", "decreased"),
        ("increase", "decrease"),
        ("improved", "worsened"),
        ("improve", "worsen"),
        ("higher", "lower"),
        ("up", "down"),
        ("true", "false"),
    )
    for source, target in replacements:
        if source in normalized:
            forms.add(normalized.replace(source, target))
    return forms


class DecisionEvaluator:
    def evaluate(
        self,
        decision: DecisionBrief,
        required_claims: Iterable[str],
    ) -> EvaluationResult:
        observed_claims = (*decision.facts, *decision.hypotheses)
        observed = {claim.casefold() for claim in observed_claims}
        required = tuple(required_claims)
        missing = tuple(claim for claim in required if claim.casefold() not in observed)
        matched = tuple(claim for claim in required if claim.casefold() in observed)
        contradictions = tuple(
            claim
            for claim in required
            if claim.casefold() not in observed
            and any(
                _claim_forms(claim) & _claim_forms(observed_claim)
                for observed_claim in observed_claims
            )
        )
        if contradictions:
            confidence = "low"
        elif required and len(matched) == len(required):
            confidence = "high"
        elif matched:
            confidence = "medium"
        else:
            confidence = "low"
        return EvaluationResult(
            passed=not missing and not contradictions,
            matched_claims=matched,
            missing_claims=missing,
            contradictions=contradictions,
            confidence=confidence,
        )
