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
            "idempotency_key": "shopping:OrderCreated:order-1",
        },
    )

    assert response.status_code == 201
    assert response.json()["event_type"] == "OrderCreated"
    events = client.get("/api/events?correlation_id=workflow-1").json()
    assert len(events) == 1
    assert events[0]["payload"] == {"total": 25.0}

    duplicate = client.post(
        "/api/events",
        json={
            "source_service": "shopping",
            "event_type": "OrderCreated",
            "aggregate_type": "order",
            "aggregate_id": "order-1",
            "payload": {"total": 99.0},
            "idempotency_key": "shopping:OrderCreated:order-1",
        },
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["event_id"] == response.json()["event_id"]
    assert duplicate.json()["payload"] == {"total": 25.0}

    replay = client.get("/api/events/replay?source_service=shopping&limit=10")
    assert replay.status_code == 200
    assert len(replay.json()) == 1


def test_contract_catalog_and_batch_replay_cursor(tmp_path):
    app_module.repository = EventRepository(tmp_path / "events.sqlite3")
    client = TestClient(app_module.app)
    batch = client.post("/api/events/batch", json={"events": [{
        "source_service": "content-site", "event_type": "PageVisit", "aggregate_type": "content_session",
        "aggregate_id": "session-1", "correlation_id": "session-1", "payload": {"session_id": "session-1"},
    }, {
        "source_service": "content-site", "event_type": "Exit", "aggregate_type": "content_session",
        "aggregate_id": "session-1", "correlation_id": "session-1", "payload": {"session_id": "session-1"},
    }]})
    assert batch.status_code == 201
    events = batch.json()
    assert client.get("/api/contracts").json()["content-site"]
    replay = client.get(f"/api/events/replay?after_event_id={events[0]['event_id']}")
    assert [event["event_type"] for event in replay.json()] == ["Exit"]

    invalid = client.post("/api/events", json={
        "source_service": "content-site", "event_type": "Unknown", "aggregate_type": "x", "aggregate_id": "x", "payload": {}
    })
    assert invalid.status_code == 422
