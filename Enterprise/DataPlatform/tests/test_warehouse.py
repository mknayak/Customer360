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


def test_order_backfill_replaces_event_stub_with_items(tmp_path):
    warehouse = EventWarehouse(tmp_path / "analytics.sqlite3")
    warehouse.ingest([{"event_id": "order-1", "source_service": "shopping", "event_type": "OrderCreated", "aggregate_type": "order", "aggregate_id": "order-1", "occurred_at": "2026-01-01T00:00:00Z", "payload": {"customer_id": "customer-1", "payment_status": "succeeded"}}])
    warehouse.ingest([{"event_id": "order-backfill-1", "source_service": "shopping", "event_type": "OrderCreated", "aggregate_type": "order", "aggregate_id": "order-1", "occurred_at": "2026-01-01T00:00:00Z", "payload": {"customer_id": "customer-1", "payment_status": "succeeded", "total_amount": 25, "items": [{"product_id": "product-1", "quantity": 2, "unit_price": 12.5}]}}])

    assert warehouse.kpi("product_performance")["value"] == [{"product_id": "product-1", "units": 2, "revenue": 25.0}]
    warehouse.close()


def test_retention_kpi_measures_repeat_successful_customers(tmp_path):
    warehouse = EventWarehouse(tmp_path / "analytics.sqlite3")
    events = [
        {"event_id": "order-1", "source_service": "shopping", "event_type": "OrderCreated", "aggregate_type": "order", "aggregate_id": "order-1", "occurred_at": "2026-01-01T00:00:00Z", "payload": {"customer_id": "customer-1", "payment_status": "succeeded"}},
        {"event_id": "order-2", "source_service": "shopping", "event_type": "OrderCreated", "aggregate_type": "order", "aggregate_id": "order-2", "occurred_at": "2026-01-02T00:00:00Z", "payload": {"customer_id": "customer-1", "payment_status": "succeeded"}},
        {"event_id": "order-3", "source_service": "shopping", "event_type": "OrderCreated", "aggregate_type": "order", "aggregate_id": "order-3", "occurred_at": "2026-01-02T00:00:00Z", "payload": {"customer_id": "customer-2", "payment_status": "succeeded"}},
    ]
    warehouse.ingest(events)

    assert warehouse.kpi("retention")["value"] == 0.5
    warehouse.close()


def test_content_and_finance_models_are_curated(tmp_path):
    warehouse = EventWarehouse(tmp_path / "analytics.sqlite3")
    warehouse.ingest([
        {"event_id": "session-1", "source_service": "content-site", "event_type": "PageVisit", "aggregate_type": "content_session", "aggregate_id": "session-1", "correlation_id": "session-1", "occurred_at": "2026-01-01T00:00:00Z", "payload": {"session_id": "session-1"}},
        {"event_id": "view-1", "source_service": "content-site", "event_type": "ContentView", "aggregate_type": "content_page", "aggregate_id": "about", "correlation_id": "session-1", "occurred_at": "2026-01-01T00:01:00Z", "payload": {"session_id": "session-1", "content_id": "about"}},
        {"event_id": "time-1", "source_service": "content-site", "event_type": "TimeOnPage", "aggregate_type": "content_page", "aggregate_id": "about", "correlation_id": "session-1", "occurred_at": "2026-01-01T00:02:00Z", "payload": {"session_id": "session-1", "duration_seconds": 20}},
        {"event_id": "finance-1", "source_service": "shopping", "event_type": "OrderCreated", "aggregate_type": "order", "aggregate_id": "order-1", "occurred_at": "2026-01-01T00:03:00Z", "payload": {"customer_id": "customer-1", "payment_status": "succeeded", "total_amount": 100, "cost_amount": 60, "promotion_id": "promotion-1"}},
    ])
    assert warehouse.kpi("content_views")["value"] == 1
    assert warehouse.kpi("content_sessions")["value"] == 1
    assert warehouse.kpi("average_time_on_page")["value"] == 20
    assert warehouse.kpi("profit")["value"] == 40
    assert warehouse.kpi("gross_margin")["value"] == 0.4
    assert warehouse.quality()["curated_tables"]["finance"] == 1
    warehouse.close()