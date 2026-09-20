from data_platform.warehouse import EventWarehouse


def test_ingestion_is_idempotent_and_builds_curated_kpis(tmp_path):
    warehouse = EventWarehouse(tmp_path / "analytics.sqlite3")
    events = [
        {"event_id": "visit-1", "source_service": "site", "event_type": "VisitStarted", "aggregate_type": "visit", "aggregate_id": "visit-1", "occurred_at": "2026-01-01T00:00:00Z", "payload": {"customer_id": "customer-1", "site_id": "site-1"}},
        {"event_id": "cart-1", "source_service": "shopping", "event_type": "CartCreated", "aggregate_type": "cart", "aggregate_id": "cart-1", "occurred_at": "2026-01-01T00:01:00Z", "payload": {"customer_id": "customer-1"}},
        {"event_id": "order-1", "source_service": "shopping", "event_type": "OrderCreated", "aggregate_type": "order", "aggregate_id": "order-1", "occurred_at": "2026-01-01T00:02:00Z", "payload": {"customer_id": "customer-1", "payment_status": "succeeded", "total_amount": 25, "items": [{"product_id": "product-1", "quantity": 2, "unit_price": 12.5}]}},
    ]

    assert warehouse.ingest(events) == {"received": 3, "stored": 3, "duplicates": 0}
    assert warehouse.ingest(events) == {"received": 3, "stored": 0, "duplicates": 3}
    assert warehouse.kpi("revenue")["value"] == 25.0
    assert warehouse.kpi("visits")["value"] == 1
    assert warehouse.kpi("conversion")["value"] == 1.0
    assert warehouse.kpi("product_performance")["value"][0]["units"] == 2
    warehouse.close()


def test_cart_abandonment_kpi_is_curated_from_events(tmp_path):
    warehouse = EventWarehouse(tmp_path / "analytics.sqlite3")
    base = {"source_service": "shopping", "aggregate_type": "cart", "occurred_at": "2026-01-01T00:00:00Z", "payload": {}}
    warehouse.ingest([{**base, "event_id": "cart-1", "event_type": "CartCreated", "aggregate_id": "cart-1"}, {**base, "event_id": "cart-2", "event_type": "CartCreated", "aggregate_id": "cart-2"}, {**base, "event_id": "abandon-1", "event_type": "CartAbandoned", "aggregate_id": "cart-1"}])

    assert warehouse.kpi("cart_abandonment")["value"] == 0.5
    warehouse.close()