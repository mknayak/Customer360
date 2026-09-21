from fastapi.testclient import TestClient

from Agent.app.evaluation import TARGET_QUESTIONS, evaluate_target_questions
from Agent.app.main import app


def test_target_question_evaluation_report_is_complete():
    report = evaluate_target_questions(TestClient(app))

    assert report.total == len(TARGET_QUESTIONS) == 6
    assert report.failed == 0
    assert report.groundedness_rate == 1.0
    assert all(result.has_answer and result.has_evidence for result in report.results)


def test_target_question_evaluation_fails_closed_for_unknown_principal():
    report = evaluate_target_questions(TestClient(app), principal_id="unknown-principal")

    assert report.failed == 6
    assert report.groundedness_rate == 0.0
    assert all(result.status_code == 403 for result in report.results)
