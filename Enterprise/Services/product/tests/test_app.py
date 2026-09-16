from fastapi.testclient import TestClient

from product_service import app as app_module
from product_service.repository import ProductRepository


def test_product_and_promotion_api(monkeypatch, tmp_path):
    repository = ProductRepository(tmp_path / "product.sqlite3")
    monkeypatch.setattr(app_module, "repository", repository)
    client = TestClient(app_module.app)
    assert client.get("/api/health").json() == {"status": "ok", "service": "product"}
    product = client.post("/api/products", json={"sku": "SKU-1", "name": "Coffee"})
    assert product.status_code == 201
    product_id = product.json()["product_id"]
    price = client.post(f"/api/products/{product_id}/prices", json={"amount": 12.5, "currency": "USD"})
    assert price.status_code == 201
    promotion = client.post("/api/promotions", json={"name": "Launch", "discount_type": "percentage", "discount_value": 10, "start_date": "2026-01-01T00:00:00Z", "product_ids": [product_id]})
    assert promotion.status_code == 201
    assert promotion.json()["product_ids"] == [product_id]
    repository.close()


def test_store_catalog_and_inventory(monkeypatch, tmp_path):
    repository = ProductRepository(tmp_path / "product.sqlite3")
    monkeypatch.setattr(app_module, "repository", repository)
    client = TestClient(app_module.app)
    product_id = client.post("/api/products", json={"sku": "SKU-STORE", "name": "Store product"}).json()["product_id"]
    store_id = client.post("/api/stores", json={"name": "Central", "channel": "physical"}).json()["store_id"]
    catalog = client.post(f"/api/stores/{store_id}/catalog", json={"product_id": product_id, "price_amount": 19.99, "currency": "USD"})
    assert catalog.status_code == 201
    inventory = client.post(f"/api/stores/{store_id}/inventory", json={"product_id": product_id, "quantity": 10, "reserved_quantity": 2})
    assert inventory.status_code == 201
    assert inventory.json()["quantity"] == 10
    assert client.get(f"/api/stores/{store_id}/catalog").json()[0]["product_id"] == product_id
    repository.close()
