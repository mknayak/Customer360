import pytest

from data_platform.semantic_query import QueryPolicyGate
from data_platform.text_to_sql import SQLValidationError, TextToSQLService
from data_platform.warehouse import EventWarehouse


@pytest.fixture()
def service(tmp_path):
    warehouse = EventWarehouse(tmp_path / "analytics.sqlite3")
    warehouse.ingest([
        {"event_id": "category-1", "source_service": "product", "event_type": "CategoryCreated", "aggregate_type": "category", "aggregate_id": "cat-kitchen", "occurred_at": "2026-01-01T00:00:00Z", "payload": {"category_id": "cat-kitchen", "name": "Kitchen"}},
        {"event_id": "product-1", "source_service": "product", "event_type": "ProductCreated", "aggregate_type": "product", "aggregate_id": "p-1", "occurred_at": "2026-01-01T00:00:00Z", "payload": {"product_id": "p-1", "sku": "SKU-1", "name": "Kettle", "category_id": "cat-kitchen", "brand": "Northstar", "status": "active"}},
        {"event_id": "order-1", "source_service": "shopping", "event_type": "OrderCreated", "aggregate_type": "order", "aggregate_id": "o-1", "occurred_at": "2026-01-02T00:00:00Z", "payload": {"customer_id": "c-1", "payment_status": "succeeded", "total_amount": 40, "items": [{"product_id": "p-1", "quantity": 2, "unit_price": 10}, {"product_id": "p-2", "quantity": 1, "unit_price": 20}]}},
        {"event_id": "order-2", "source_service": "shopping", "event_type": "OrderCreated", "aggregate_type": "order", "aggregate_id": "o-2", "occurred_at": "2026-01-03T00:00:00Z", "payload": {"customer_id": "c-2", "payment_status": "failed", "total_amount": 99, "items": [{"product_id": "p-1", "quantity": 9, "unit_price": 11}]}},
    ])
    with warehouse.connection:
        warehouse.connection.executemany(
            "INSERT INTO dim_customer_profiles VALUES (?, ?, ?, ?, ?, ?, ?)",
            [("c-1", "55-64", "London", "GB", "email", "active", "2026-01-01"),
             ("c-2", "45-54", "Paris", "FR", "sms", "active", "2026-01-01")],
        )
    policy = QueryPolicyGate({"cfo-1": ("digital", "commerce", "finance", "customer"), "digital-analyst": ("digital",)})
    text_to_sql = TextToSQLService(warehouse.database_path, policy=policy)
    text_to_sql.refresh()
    yield text_to_sql
    warehouse.close()


def test_context_links_category_to_revenue_through_join_graph(service):
    context = service.context("Which category contributes most revenue?", "cfo-1")

    tables = [table["name"] for table in context["tables"]]
    assert {"dim_categories", "dim_products", "curated_order_items", "curated_orders"} <= set(tables)
    joins = {(join["left"], join["right"]) for join in context["join_paths"]}
    assert ("dim_products.category_id", "dim_categories.category_id") in joins
    assert ("curated_order_items.product_id", "dim_products.product_id") in joins
    assert any("payment_status = 'succeeded'" in rule for rule in context["business_rules"])
    orders = next(table for table in context["tables"] if table["name"] == "curated_orders")
    assert next(column for column in orders["columns"] if column["name"] == "payment_status")["values"]


def test_context_withholds_unauthorized_domains(service):
    context = service.context("Which category contributes most revenue?", "digital-analyst")

    assert all(table["domain"] == "digital" for table in context["tables"])
    assert context["withheld_table_count"] > 0
    with pytest.raises(PermissionError):
        service.context("revenue", "unknown-principal")


def test_context_links_product_sales_to_customer_age_and_flags_40_plus_limit(service):
    context = service.context("Which products are most attractive to customers age 40+?", "cfo-1")

    tables = {table["name"] for table in context["tables"]}
    assert {"curated_order_items", "curated_orders", "dim_products", "dim_customer_profiles"} <= tables
    joins = {(join["left"], join["right"]) for join in context["join_paths"]}
    assert ("curated_orders.customer_id", "dim_customer_profiles.customer_id") in joins
    assert any("exact 40+ cohort is not derivable" in rule for rule in context["business_rules"])


def test_context_exposes_feedback_for_customer_complaints(service):
    context = service.context("What are the top customer complaints this month?", "cfo-1")

    tables = {table["name"] for table in context["tables"]}
    assert "curated_feedback" in tables
    feedback = next(table for table in context["tables"] if table["name"] == "curated_feedback")
    assert {"rating", "comment", "sentiment", "occurred_at"} <= {column["name"] for column in feedback["columns"]}
    assert any("rating <= 2" in rule and "negative" in rule for rule in context["business_rules"])
    assert ("curated_feedback.customer_id", "dim_customer_profiles.customer_id") in {
        (join["left"], join["right"]) for join in context["join_paths"]
    }


def test_execute_runs_generated_category_sql_read_only(service):
    result = service.execute(
        """
        WITH lines AS (
            SELECT COALESCE(c.name, 'Uncategorized') AS category, i.revenue
            FROM curated_order_items i
            JOIN curated_orders o ON o.order_id = i.order_id AND o.payment_status = 'succeeded'
            LEFT JOIN dim_products p ON p.product_id = i.product_id
            LEFT JOIN dim_categories c ON c.category_id = p.category_id
        )
        SELECT category, ROUND(SUM(revenue), 2) AS revenue FROM lines GROUP BY category ORDER BY revenue DESC, category; -- ranked
        """,
        "cfo-1",
    )

    assert result["rows"] == [{"category": "Kitchen", "revenue": 20.0}, {"category": "Uncategorized", "revenue": 20.0}]
    assert set(result["tables"]) == {"curated_order_items", "curated_orders", "dim_products", "dim_categories"}
    assert result["query_id"] and result["data_classification"] == "synthetic"


def test_execute_ranks_products_for_selected_older_age_bands(service):
    result = service.execute(
        """
        SELECT p.name AS product_name, SUM(i.quantity) AS total_units_sold
        FROM curated_order_items AS i
        JOIN curated_orders AS o ON o.order_id = i.order_id
        JOIN dim_customer_profiles AS c ON c.customer_id = o.customer_id
        JOIN dim_products AS p ON p.product_id = i.product_id
        WHERE o.payment_status = 'succeeded' AND c.age_group IN ('45-54', '55-64')
        GROUP BY p.name ORDER BY total_units_sold DESC
        """,
        "cfo-1",
    )

    assert result["rows"] == [{"product_name": "Kettle", "total_units_sold": 2}]
    assert "dim_customer_profiles" in result["tables"]


@pytest.mark.parametrize("sql", [
    "DELETE FROM curated_orders",
    "SELECT 1; DROP TABLE raw_events",
    "WITH d AS (SELECT 1) DELETE FROM raw_events",
    "SELECT load_extension('x')",
    "SELECT * FROM missing_table",
])
def test_execute_rejects_non_read_only_or_invalid_sql(service, sql):
    with pytest.raises(SQLValidationError):
        service.execute(sql, "cfo-1")


def test_execute_denies_tables_outside_grant_and_system_catalog(service):
    with pytest.raises(PermissionError):
        service.execute("SELECT name FROM sqlite_master", "cfo-1")
    with pytest.raises(PermissionError):
        service.execute("SELECT SUM(total_amount) FROM curated_orders", "digital-analyst")
    with pytest.raises(PermissionError):
        service.execute("WITH sqlite_master AS (SELECT 1) SELECT * FROM curated_orders", "digital-analyst")


def test_execute_caps_rows_and_allows_recursive_cte(service):
    result = service.execute("WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n WHERE x < 500) SELECT x FROM n", "cfo-1", limit=10)

    assert result["row_count"] == 10
    assert result["truncated"] is True


def test_execute_times_out_runaway_queries(service):
    service.timeout_seconds = 0.2
    with pytest.raises(SQLValidationError, match="time budget"):
        service.execute("WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) SELECT COUNT(*) FROM n", "cfo-1")
