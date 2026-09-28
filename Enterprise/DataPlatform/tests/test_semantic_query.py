import json
from io import BytesIO

from fastapi.testclient import TestClient

from data_platform import app as app_module
from data_platform.semantic_query import JoinSpec, MetricSpec, SQLCompiler, SemanticQueryIR, SemanticQueryPlanner
from data_platform.warehouse import EventWarehouse


def _warehouse(tmp_path):
    warehouse = EventWarehouse(tmp_path / "analytics.sqlite3")
    warehouse.ingest([
        {"event_id": "exit-1", "source_service": "content-site", "event_type": "Exit", "aggregate_type": "content_session", "aggregate_id": "s1", "correlation_id": "s1", "occurred_at": "2026-01-01T00:00:00Z", "payload": {"session_id": "s1", "last_page": "products"}},
        {"event_id": "exit-2", "source_service": "content-site", "event_type": "Exit", "aggregate_type": "content_session", "aggregate_id": "s2", "correlation_id": "s2", "occurred_at": "2026-01-01T00:01:00Z", "payload": {"session_id": "s2", "last_page": "products"}},
        {"event_id": "exit-3", "source_service": "content-site", "event_type": "Exit", "aggregate_type": "content_session", "aggregate_id": "s3", "correlation_id": "s3", "occurred_at": "2026-01-01T00:02:00Z", "payload": {"session_id": "s3", "last_page": "about"}},
        {"event_id": "view-1", "source_service": "content-site", "event_type": "ContentView", "aggregate_type": "content_page", "aggregate_id": "products", "correlation_id": "s1", "occurred_at": "2026-01-01T00:00:00Z", "payload": {"session_id": "s1", "content_id": "products"}},
    ])
    return warehouse


def test_metadata_retrieval_returns_compact_relevant_context():
    context = SemanticQueryPlanner().context("What is the most dropped page?", limit=2)

    assert context["domains"] == ("digital",)
    assert context["candidates"][0]["metric"] == "page_dropoff"
    assert context["candidates"][0]["model"] == "curated_content_activity"
    assert "page" in context["candidates"][0]["dimensions"]

    popular = SemanticQueryPlanner().context("What is the most visited page?", limit=1)
    assert popular["candidates"][0]["metric"] == "page_popularity"

    payment_failures = SemanticQueryPlanner().context("How many times payment failed?", limit=1)
    assert payment_failures["candidates"][0]["metric"] == "payment_failures"


def test_sql_compiler_resolves_catalog_owned_join_chain():
    metric = MetricSpec(
        "order_item_revenue",
        "Order item revenue",
        "commerce",
        "Revenue by product and customer",
        (),
        "curated_order_items",
        "SUM(base.revenue)",
        "value",
        {"customer": "orders.customer_id", "product": "base.product_id"},
        {},
        joins={
            "orders": JoinSpec("orders", "curated_orders", "orders", "base", "order_id", "order_id"),
        },
    )

    compiled = SQLCompiler().compile(SemanticQueryIR("order_item_revenue", ("customer", "product"), joins=("orders",)), metric)

    assert "JOIN curated_orders AS orders ON base.order_id = orders.order_id" in compiled.sql
    assert "SELECT orders.customer_id AS customer, base.product_id AS product" in compiled.sql


def test_sql_compiler_rejects_unknown_join():
    metric = MetricSpec("revenue", "Revenue", "finance", "Revenue", (), "curated_orders", "SUM(total_amount)", "value", {}, {})

    try:
        SQLCompiler().compile(SemanticQueryIR("revenue", joins=("customers",)), metric)
    except ValueError as error:
        assert "Unsupported join" in str(error)
    else:
        raise AssertionError("Unknown joins must not reach SQL compilation")


def test_planner_compiles_and_executes_allowlisted_page_dropoff_query(tmp_path):
    planner = SemanticQueryPlanner()
    warehouse = _warehouse(tmp_path)
    compiled = planner.plan(SemanticQueryIR("page_dropoff", limit=10), "cfo-1")
    result = warehouse.execute_semantic(compiled)

    assert result["rows"] == [{"page": "products", "exits": 2}, {"page": "about", "exits": 1}]
    assert "event_type = 'Exit'" in result["query"]["sql"]
    assert result["lineage"] == ("Exit", "curated_content_activity")
    warehouse.close()


def test_payment_failures_counts_payment_failed_events(tmp_path):
    warehouse = EventWarehouse(tmp_path / "analytics.sqlite3")
    warehouse.ingest([
        {"event_id": "payment-failed-1", "source_service": "shopping", "event_type": "PaymentFailed", "aggregate_type": "order", "aggregate_id": "order-1", "occurred_at": "2026-01-01T00:00:00Z", "payload": {"failure_reason": "declined"}},
        {"event_id": "payment-failed-2", "source_service": "shopping", "event_type": "PaymentFailed", "aggregate_type": "order", "aggregate_id": "order-2", "occurred_at": "2026-01-01T00:01:00Z", "payload": {"failure_reason": "expired_card"}},
    ])

    planner = SemanticQueryPlanner()
    compiled = planner.plan(SemanticQueryIR("payment_failures"), "cfo-1")
    result = warehouse.execute_semantic(compiled)

    assert result["rows"] == [{"value": 2}]
    assert result["lineage"] == ("PaymentFailed", "raw_events")
    assert warehouse.kpi("payment_failures")["value"] == 2
    warehouse.close()


def test_payment_failures_can_group_by_customer_from_event_payload(tmp_path):
    warehouse = EventWarehouse(tmp_path / "analytics.sqlite3")
    warehouse.ingest([
        {"event_id": "payment-failed-customer-1", "source_service": "shopping", "event_type": "PaymentFailed", "aggregate_type": "order", "aggregate_id": "order-1", "occurred_at": "2026-01-01T00:00:00Z", "payload": {"customer_id": "customer-1", "failure_reason": "declined"}},
        {"event_id": "payment-failed-customer-2", "source_service": "shopping", "event_type": "PaymentFailed", "aggregate_type": "order", "aggregate_id": "order-2", "occurred_at": "2026-01-01T00:01:00Z", "payload": {"customer_id": "customer-1", "failure_reason": "expired_card"}},
        {"event_id": "payment-failed-customer-3", "source_service": "shopping", "event_type": "PaymentFailed", "aggregate_type": "order", "aggregate_id": "order-3", "occurred_at": "2026-01-01T00:02:00Z", "payload": {"customer_id": "customer-2", "failure_reason": "declined"}},
    ])

    compiled = SemanticQueryPlanner().plan(SemanticQueryIR("payment_failures", dimensions=("customer",)), "cfo-1")
    result = warehouse.execute_semantic(compiled)

    assert result["rows"] == [{"customer": "customer-1", "value": 2}, {"customer": "customer-2", "value": 1}]
    warehouse.close()


def test_payment_failures_by_profile_uses_order_customer_and_suppresses_small_groups(tmp_path):
    warehouse = EventWarehouse(tmp_path / "analytics.sqlite3")
    for index, customer in enumerate(("a", "d", "e", "b", "c")):
        warehouse.ingest([
            {"event_id": f"order-{index}", "source_service": "shopping", "event_type": "OrderCreated", "aggregate_type": "order", "aggregate_id": f"order-{index}", "occurred_at": "2026-01-01", "payload": {"customer_id": customer, "payment_status": "failed", "total_amount": 10}},
            {"event_id": f"failure-{index}", "source_service": "shopping", "event_type": "PaymentFailed", "aggregate_type": "order", "aggregate_id": f"order-{index}", "occurred_at": "2026-01-01", "payload": {"failure_reason": "declined"}},
        ])

    result = warehouse.payment_failures_by_profile("country", {"a": "US", "d": "US", "e": "US", "b": "GB"})

    assert result["rows"] == [{"group": "US", "value": 3}]
    assert result["suppressed_groups"] == 1
    assert result["unmatched_events"] == 1
    warehouse.close()


def test_payment_failure_profile_api_authorizes_before_crm_and_returns_aggregates(tmp_path, monkeypatch):
    warehouse = EventWarehouse(tmp_path / "analytics.sqlite3")
    warehouse.ingest([
        {"event_id": f"failed-{index}", "source_service": "shopping", "event_type": "PaymentFailed", "aggregate_type": "order", "aggregate_id": f"order-{index}", "occurred_at": "2026-01-01", "payload": {"customer_id": f"customer-{index}"}}
        for index in range(3)
    ])
    monkeypatch.setattr(app_module, "warehouse", warehouse)
    calls = []

    def directory(url, timeout):
        calls.append(url)
        return BytesIO(json.dumps({"items": [{"customer_id": f"customer-{index}", "country": "US", "email": "private@example.com"} for index in range(3)], "total_pages": 1}).encode())

    monkeypatch.setattr(app_module, "urlopen", directory)
    client = TestClient(app_module.app)
    denied = client.post("/api/payment-failures/by-profile", json={"principal_id": "unknown", "dimension": "country"})
    assert denied.status_code == 403
    assert calls == []

    result = client.post("/api/payment-failures/by-profile", json={"principal_id": "cfo-1", "dimension": "country"})
    assert result.status_code == 200
    assert result.json()["rows"] == [{"group": "US", "value": 3}]
    assert "private@example.com" not in result.text
    assert len(calls) == 1
    assert client.post("/api/payment-failures/by-profile", json={"principal_id": "cfo-1", "dimension": "gender"}).status_code == 422
    warehouse.close()


def test_query_ir_rejects_unknown_fields_and_fails_closed(tmp_path):
    planner = SemanticQueryPlanner()

    try:
        planner.plan(SemanticQueryIR("page_dropoff", dimensions=("raw_email",)), "cfo-1")
    except ValueError as error:
        assert "Unsupported dimensions" in str(error)
    else:
        raise AssertionError("Unknown dimensions must be rejected")

    try:
        planner.plan(SemanticQueryIR("revenue"), "unknown-principal")
    except PermissionError:
        pass
    else:
        raise AssertionError("Unknown principals must be denied")

    warehouse = _warehouse(tmp_path)
    compiled = planner.plan(SemanticQueryIR("page_dropoff", filters={"page": "products' OR 1=1 --"}), "cfo-1")
    result = warehouse.execute_semantic(compiled)
    assert result["rows"] == []
    assert "?" in result["query"]["sql"]
    warehouse.close()


def test_semantic_query_api_returns_lineage_and_denies_unknown_principal(tmp_path, monkeypatch):
    warehouse = _warehouse(tmp_path)
    monkeypatch.setattr(app_module, "warehouse", warehouse)
    client = TestClient(app_module.app)

    context = client.post("/api/semantic-query/context", json={"question": "most dropped page"})
    assert context.status_code == 200
    assert context.json()["candidates"][0]["metric"] == "page_dropoff"

    result = client.post("/api/semantic-query/execute", json={"principal_id": "cfo-1", "metric": "page_dropoff"})
    assert result.status_code == 200
    assert result.json()["rows"][0] == {"page": "products", "exits": 2}
    assert result.json()["source_model"] == "curated_content_activity"

    denied = client.post("/api/semantic-query/execute", json={"principal_id": "unknown", "metric": "page_dropoff"})
    assert denied.status_code == 403
    warehouse.close()


def test_trend_api_returns_authorized_cohort_points(tmp_path, monkeypatch):
    warehouse = EventWarehouse(tmp_path / "analytics.sqlite3")
    warehouse.ingest([
        {"event_id": event_id, "source_service": "shopping", "event_type": "OrderCreated", "aggregate_type": "order",
         "aggregate_id": event_id, "occurred_at": date + "T00:00:00Z", "payload": {"customer_id": customer, "payment_status": "succeeded", "total_amount": 10}}
        for event_id, date, customer in [("one", "2026-01-01", "a"), ("two", "2026-02-01", "a")]
    ])
    monkeypatch.setattr(app_module, "warehouse", warehouse)
    client = TestClient(app_module.app)

    result = client.post("/api/trends", json={"principal_id": "cfo-1", "metric": "retention", "granularity": "month"})
    assert result.status_code == 200
    assert result.json()["points"][1] == {"period": "2026-02", "value": 1.0, "numerator": 1, "denominator": 1}
    assert client.post("/api/trends", json={"principal_id": "unknown", "metric": "retention", "granularity": "month"}).status_code == 403
    assert client.post("/api/trends", json={"principal_id": "cfo-1", "metric": "not_a_metric", "granularity": "month"}).status_code == 400
    assert client.post("/api/trends", json={"principal_id": "cfo-1", "metric": "retention", "granularity": "year"}).status_code == 422
    revenue = client.post("/api/trends", json={"principal_id": "cfo-1", "metric": "revenue", "granularity": "month"})
    assert revenue.json()["points"] == [{"period": "2026-01", "value": 10.0}, {"period": "2026-02", "value": 10.0}]
    warehouse.close()
