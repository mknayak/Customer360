from fastapi.testclient import TestClient

from shopping_service import app as app_module
from shopping_service.repository import ShoppingRepository


def test_cart_and_order_api(monkeypatch, tmp_path):
    repository = ShoppingRepository(tmp_path / "shopping.sqlite3")
    monkeypatch.setattr(app_module, "repository", repository)
    client = TestClient(app_module.app)
    assert client.get("/api/health").json() == {"status": "ok", "service": "shopping"}
    cart = client.post("/api/carts", json={"customer_id": "customer-1", "payment_status": "pending", "payment_method": "card"})
    assert cart.status_code == 201
    assert cart.json()["payment_method"] == "card"
    cart_id = cart.json()["cart_id"]
    item = client.post(f"/api/carts/{cart_id}/items", json={"product_id": "product-1", "quantity": 2, "unit_price": 10})
    assert item.status_code == 201
    assert len(client.get(f"/api/carts/{cart_id}").json()["items"]) == 1
    order = client.post("/api/orders", json={"customer_id": "customer-1", "currency": "USD", "items": [{"product_id": "product-1", "quantity": 2, "unit_price": 10}]})
    assert order.status_code == 201
    assert order.json()["total_amount"] == 20
    repository.close()


def test_order_payment_outcomes(monkeypatch, tmp_path):
    repository = ShoppingRepository(tmp_path / "shopping.sqlite3")
    monkeypatch.setattr(app_module, "repository", repository)
    client = TestClient(app_module.app)
    base = {
        "customer_id": "customer-1",
        "currency": "USD",
        "items": [{"product_id": "product-1", "quantity": 1, "unit_price": 25}],
    }

    pending = client.post("/api/orders", json={**base, "payment_status": "pending", "payment_method": "card"})
    assert pending.status_code == 201
    assert pending.json()["status"] == "pending_payment"

    failed = client.post("/api/orders", json={**base, "payment_status": "failed", "failure_reason": "declined", "payment_method": "card"})
    assert failed.status_code == 201
    assert failed.json()["status"] == "payment_failed"
    assert failed.json()["failure_reason"] == "declined"

    succeeded = client.post("/api/orders", json={**base, "payment_status": "succeeded", "payment_method": "card", "transaction_id": "txn-123"})
    assert succeeded.status_code == 201
    assert succeeded.json()["status"] == "created"
    assert succeeded.json()["paid_at"] is not None
    assert succeeded.json()["transaction_id"] == "txn-123"

    invalid = client.post("/api/orders", json={**base, "payment_status": "failed"})
    assert invalid.status_code == 400
    repository.close()
