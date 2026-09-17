from fastapi.testclient import TestClient

from feedback_service import app as app_module
from feedback_service.repository import FeedbackRepository


def test_feedback_api(monkeypatch, tmp_path):
    repository = FeedbackRepository(tmp_path / "feedback.sqlite3")
    monkeypatch.setattr(app_module, "repository", repository)
    client = TestClient(app_module.app)

    assert client.get("/api/health").json() == {"status": "ok", "service": "feedback"}

    created = client.post(
        "/api/feedback",
        json={
            "customer_id": "customer-1",
            "source": "survey",
            "rating": 4,
            "comment": "Helpful support follow-up",
            "campaign_id": "campaign-1",
            "sentiment": "positive",
        },
    )
    assert created.status_code == 201
    feedback_id = created.json()["feedback_id"]

    listed = client.get("/api/feedback?customer_id=customer-1").json()
    assert len(listed) == 1
    assert listed[0]["feedback_id"] == feedback_id
    assert listed[0]["campaign_id"] == "campaign-1"

    updated = client.put(f"/api/feedback/{feedback_id}", json={"rating": 3, "status": "reviewed"})
    assert updated.status_code == 200
    assert updated.json()["rating"] == 3
    assert updated.json()["status"] == "reviewed"

    deleted = client.delete(f"/api/feedback/{feedback_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/feedback/{feedback_id}").status_code == 404
    repository.close()


def test_feedback_validates_rating(monkeypatch, tmp_path):
    repository = FeedbackRepository(tmp_path / "feedback.sqlite3")
    monkeypatch.setattr(app_module, "repository", repository)
    client = TestClient(app_module.app)

    response = client.post("/api/feedback", json={"customer_id": "customer-1", "source": "web", "rating": 6})
    assert response.status_code == 422
    repository.close()
