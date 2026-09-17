from fastapi.testclient import TestClient

from marketing_service import app as app_module
from marketing_service.repository import MarketingRepository


def test_marketing_campaign_audience_and_channel_api(monkeypatch, tmp_path):
    repository = MarketingRepository(tmp_path / "marketing.sqlite3")
    monkeypatch.setattr(app_module, "repository", repository)
    client = TestClient(app_module.app)

    assert client.get("/api/health").json() == {"status": "ok", "service": "marketing"}

    campaign = client.post(
        "/api/campaigns",
        json={
            "name": "Launch loyalty offer",
            "objective": "Increase repeat purchase",
            "status": "scheduled",
            "start_date": "2026-01-01T00:00:00Z",
            "budget_amount": 2500,
        },
    )
    assert campaign.status_code == 201
    campaign_id = campaign.json()["campaign_id"]

    audience = client.post(
        "/api/audiences",
        json={"name": "Loyal customers", "segment": "loyal", "criteria": {"segment": "gold"}},
    )
    assert audience.status_code == 201
    audience_id = audience.json()["audience_id"]

    channel = client.post("/api/channels", json={"name": "Lifecycle email", "channel_type": "email", "provider": "internal"})
    assert channel.status_code == 201
    channel_id = channel.json()["channel_id"]

    audience_link = client.post(f"/api/campaigns/{campaign_id}/audiences", json={"audience_id": audience_id})
    assert audience_link.status_code == 201
    assert client.get(f"/api/campaigns/{campaign_id}/audiences").json()[0]["audience_id"] == audience_id

    channel_link = client.post(f"/api/campaigns/{campaign_id}/channels", json={"channel_id": channel_id, "allocation_percent": 75})
    assert channel_link.status_code == 201
    assert client.get(f"/api/campaigns/{campaign_id}/channels").json()[0]["allocation_percent"] == 75

    interaction = client.post(
        f"/api/campaigns/{campaign_id}/interactions",
        json={"customer_id": "customer-1", "event_type": "clicked", "channel_id": channel_id},
    )
    assert interaction.status_code == 201
    assert client.get("/api/interactions?customer_id=customer-1").json()[0]["event_type"] == "clicked"

    updated = client.put(f"/api/campaigns/{campaign_id}", json={"status": "active"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "active"

    assert client.get("/api/campaigns?status=active").json()[0]["campaign_id"] == campaign_id
    repository.close()


def test_campaign_dates_are_validated(monkeypatch, tmp_path):
    repository = MarketingRepository(tmp_path / "marketing.sqlite3")
    monkeypatch.setattr(app_module, "repository", repository)
    client = TestClient(app_module.app)

    response = client.post(
        "/api/campaigns",
        json={
            "name": "Invalid campaign",
            "start_date": "2026-02-01T00:00:00Z",
            "end_date": "2026-01-01T00:00:00Z",
        },
    )
    assert response.status_code == 400
    repository.close()


def test_campaign_assignment_requires_existing_resources(monkeypatch, tmp_path):
    repository = MarketingRepository(tmp_path / "marketing.sqlite3")
    monkeypatch.setattr(app_module, "repository", repository)
    client = TestClient(app_module.app)

    campaign_id = client.post("/api/campaigns", json={"name": "Campaign"}).json()["campaign_id"]
    response = client.post(f"/api/campaigns/{campaign_id}/audiences", json={"audience_id": "missing"})
    assert response.status_code == 404
    repository.close()
