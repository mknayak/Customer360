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


class DecisionEvaluator:
    def evaluate(
        self,
        decision: DecisionBrief,
        required_claims: Iterable[str],
    ) -> EvaluationResult:
        observed = {claim.casefold() for claim in (*decision.facts, *decision.hypotheses)}
        required = tuple(required_claims)
        missing = tuple(claim for claim in required if claim.casefold() not in observed)
        matched = tuple(claim for claim in required if claim.casefold() in observed)
        return EvaluationResult(
            passed=not missing,
            matched_claims=matched,
            missing_claims=missing,
        )
