from fastapi.testclient import TestClient

from crm_service import app as app_module
from crm_service.repository import CrmRepository


def test_customer_api_contract(monkeypatch, tmp_path):
    repository = CrmRepository(tmp_path / "crm.sqlite3")
    monkeypatch.setattr(app_module, "repository", repository)
    published = []
    monkeypatch.setattr(
        app_module,
        "publish_event",
        lambda event_type, aggregate_id, payload, *, occurred_at: published.append(
            (event_type, aggregate_id, payload, occurred_at)
        ),
    )
    client = TestClient(app_module.app)

    assert client.get("/api/health").json() == {"status": "ok", "service": "crm"}

    created = client.post(
        "/api/customers",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"},
    )
    assert created.status_code == 201
    customer_id = created.json()["customer_id"]
    assert published[0][0:2] == ("CustomerCreated", customer_id)

    profile = client.post(
        f"/api/customers/{customer_id}/profile",
        json={"city": "London", "preferred_channel": "email"},
    )
    assert profile.status_code == 200
    assert profile.json()["customer_id"] == customer_id

    segment = client.post(
        f"/api/customers/{customer_id}/segments",
        json={"segment": "early-adopter"},
    )
    assert segment.status_code == 200
    assert segment.json()["customer_id"] == customer_id

    updated = client.put(f"/api/customers/{customer_id}", json={"status": "inactive"})
    assert updated.status_code == 200
    assert published[-1][0:2] == ("CustomerUpdated", customer_id)

    deleted = client.delete(f"/api/customers/{customer_id}")
    assert deleted.status_code == 204
    assert published[-1][0:2] == ("CustomerDeleted", customer_id)

    missing = client.get("/api/customers/missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"

    invalid = client.post("/api/customers", json={"first_name": "Ada"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    repository.close()


def test_bulk_customer_import_upserts_and_saves_profile(monkeypatch, tmp_path):
    repository = CrmRepository(tmp_path / "crm.sqlite3")
    monkeypatch.setattr(app_module, "repository", repository)
    client = TestClient(app_module.app)

    response = client.post(
        "/api/customers/bulk",
        json=[
            {
                "first_name": "Amara",
                "last_name": "Okafor",
                "email": "amara@example.test",
                "city": "Accra",
                "country": "GH",
            }
        ],
    )
    assert response.status_code == 200
    customer_id = response.json()[0]["customer_id"]
    assert client.get(f"/api/customers/{customer_id}/profile").json()["city"] == "Accra"

    updated = client.post(
        "/api/customers/bulk",
        json=[
            {
                "first_name": "Amara",
                "last_name": "Updated",
                "email": "amara@example.test",
            }
        ],
    )
    assert updated.json()[0]["customer_id"] == customer_id
    assert client.get(f"/api/customers/{customer_id}").json()["last_name"] == "Updated"
    repository.close()
