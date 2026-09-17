from fastapi.testclient import TestClient

from site_service import app as app_module
from site_service.repository import SiteRepository


def test_site_and_visit_api(monkeypatch, tmp_path):
    repository = SiteRepository(tmp_path / "site.sqlite3")
    monkeypatch.setattr(app_module, "repository", repository)
    client = TestClient(app_module.app)

    assert client.get("/api/health").json() == {"status": "ok", "service": "site"}

    site = client.post(
        "/api/sites",
        json={
            "name": "Downtown Flagship",
            "type": "STORE",
            "city": "Seattle",
            "country": "USA",
            "status": "open",
        },
    )
    assert site.status_code == 201
    site_id = site.json()["site_id"]

    visit = client.post(
        "/api/visits",
        json={
            "customer_id": "customer-123",
            "site_id": site_id,
            "channel": "web",
        },
    )
    assert visit.status_code == 201
    visit_id = visit.json()["visit_id"]
    assert visit.json()["site_id"] == site_id

    fetched = client.get(f"/api/visits/{visit_id}")
    assert fetched.status_code == 200
    assert fetched.json()["customer_id"] == "customer-123"

    repository.close()


def test_site_update_and_listing(monkeypatch, tmp_path):
    repository = SiteRepository(tmp_path / "site.sqlite3")
    monkeypatch.setattr(app_module, "repository", repository)
    client = TestClient(app_module.app)

    created = client.post(
        "/api/sites",
        json={"name": "Web Store", "type": "WEBSITE", "city": "Austin", "country": "USA", "status": "active"},
    )
    site_id = created.json()["site_id"]

    updated = client.put(
        f"/api/sites/{site_id}",
        json={"name": "Web Store", "status": "active", "city": "Dallas"},
    )
    assert updated.status_code == 200
    assert updated.json()["city"] == "Dallas"

    listing = client.get("/api/sites")
    assert listing.status_code == 200
    assert len(listing.json()) >= 1

    repository.close()
