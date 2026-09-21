"""Repeatable evaluation fixtures for the target executive questions."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Protocol


class BriefClient(Protocol):
    def post(self, path: str, *, json: dict[str, Any]): ...


TARGET_QUESTIONS = (
    "Which customer segments responded best to the latest campaign?",
    "Why did cart abandonment increase for mobile users this week?",
    "Which products are underperforming relative to forecast?",
    "Did the new promotion increase revenue or only traffic?",
    "What customer issues are correlated with lower repeat purchase rates?",
    "Which site or region is showing the strongest conversion trend?",
)


@dataclass(frozen=True)
class EvaluationResult:
    question: str
    passed: bool
    status_code: int
    response_status: str | None
    has_answer: bool
    has_evidence: bool
    has_limitations: bool
    error: str | None = None


@dataclass(frozen=True)
class EvaluationReport:
    total: int
    passed: int
    failed: int
    results: tuple[EvaluationResult, ...]

    @property
    def groundedness_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "groundedness_rate": self.groundedness_rate,
            "results": [asdict(result) for result in self.results],
        }


def evaluate_target_questions(client: BriefClient, principal_id: str = "cfo-1") -> EvaluationReport:
    results: list[EvaluationResult] = []
    for question in TARGET_QUESTIONS:
        response = client.post("/api/executive/brief", json={"prompt": question, "principal_id": principal_id})
        body = response.json()
        has_answer = bool(body.get("answer"))
        has_evidence = bool(body.get("evidence"))
        has_limitations = "limitations" in body
        passed = response.status_code == 200 and has_answer and has_evidence and has_limitations
        results.append(EvaluationResult(question, passed, response.status_code, body.get("status"), has_answer, has_evidence, has_limitations, None if passed else str(body.get("detail", "brief contract failed"))))
    return EvaluationReport(len(results), sum(result.passed for result in results), sum(not result.passed for result in results), tuple(results))
