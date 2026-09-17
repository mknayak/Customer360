from fastapi.testclient import TestClient

from orchestration_service import app as app_module


class FakeClient:
    def __init__(self):
        self.calls = []
        self.counter = 0

    def post(self, service, path, payload):
        self.calls.append((service, path, payload))
        if service == "site":
            return {"visit_id": "visit-1"}
        if service == "shopping" and path == "/api/carts":
            return {"cart_id": "cart-1"}
        if service == "events":
            self.counter += 1
            return {"event_id": f"event-{self.counter}"}
        return {"cart_item_id": "item-1"}


def test_shopping_journey_coordinates_services_and_events(monkeypatch):
    fake_client = FakeClient()
    monkeypatch.setattr(app_module, "client", fake_client)
    client = TestClient(app_module.app)

    response = client.post(
        "/api/workflows/shopping-journey",
        json={
            "customer_id": "customer-1",
            "site_id": "site-1",
            "store_id": "store-1",
            "items": [{"product_id": "product-1", "quantity": 2, "unit_price": 15.0}],
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "completed"
    assert response.json()["published_event_ids"] == ["event-1", "event-2"]
    assert [call[0] for call in fake_client.calls] == ["site", "events", "shopping", "shopping", "events"]
