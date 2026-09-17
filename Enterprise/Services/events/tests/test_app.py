from fastapi.testclient import TestClient

from event_service import app as app_module
from event_service.repository import EventRepository


def test_event_can_be_appended_and_filtered(tmp_path):
    app_module.repository = EventRepository(tmp_path / "events.sqlite3")
    client = TestClient(app_module.app)

    response = client.post(
        "/api/events",
        json={
            "source_service": "shopping",
            "event_type": "OrderCreated",
            "aggregate_type": "order",
            "aggregate_id": "order-1",
            "payload": {"total": 25.0},
            "correlation_id": "workflow-1",
        },
    )

    assert response.status_code == 201
    assert response.json()["event_type"] == "OrderCreated"
    events = client.get("/api/events?correlation_id=workflow-1").json()
    assert len(events) == 1
    assert events[0]["payload"] == {"total": 25.0}
