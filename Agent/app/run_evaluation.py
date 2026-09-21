"""Run the Customer360 executive-question evaluation suite locally."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from .evaluation import evaluate_target_questions
from .main import app


def main() -> None:
    report = evaluate_target_questions(TestClient(app))
    print(json.dumps(report.as_dict(), indent=2))
    raise SystemExit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()
