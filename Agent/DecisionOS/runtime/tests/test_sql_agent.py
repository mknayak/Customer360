import json

from decision_os.model_provider import ModelResponse
from decision_os.sql_agent import SQLAgent, SQLExecutionError, render_schema_context


CONTEXT = {
    "dialect": "sqlite",
    "tables": [
        {"name": "curated_order_items", "domain": "commerce", "grain": "line", "row_count": 3, "description": "Order lines", "columns": [{"name": "revenue", "type": "REAL", "description": "Line revenue"}]},
        {"name": "dim_categories", "domain": "commerce", "grain": "category", "row_count": 0, "description": "Categories", "columns": [{"name": "name", "type": "TEXT", "description": "Category name"}]},
    ],
    "join_paths": [{"left": "dim_products.category_id", "right": "dim_categories.category_id", "description": "product category"}],
    "business_rules": ["Revenue counts only succeeded orders."],
}


class ScriptedModel:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return ModelResponse(self.outputs.pop(0), "test", "test-model")


def test_sql_agent_repairs_invalid_sql_using_execution_error():
    model = ScriptedModel(
        json.dumps({"answerable": True, "sql": "SELECT bad FROM curated_order_items", "assumptions": []}),
        json.dumps({"answerable": True, "sql": "SELECT SUM(revenue) AS revenue FROM curated_order_items", "assumptions": ["No categories are loaded"]}),
    )
    executed = []

    def execute(sql, principal_id):
        executed.append((sql, principal_id))
        if "bad" in sql:
            raise SQLExecutionError("SQL error: no such column: bad")
        return {"query_id": "q-1", "sql": sql, "columns": ["revenue"], "rows": [{"revenue": 40.0}], "tables": ["curated_order_items"]}

    result = SQLAgent(model, lambda question, principal: CONTEXT, execute).run("Which category contributes most revenue?", "cfo-1")

    assert result.status == "answered"
    assert result.rows == [{"revenue": 40.0}]
    assert result.assumptions == ("No categories are loaded",)
    assert [attempt["error"] for attempt in result.attempts] == ["SQL error: no such column: bad", None]
    assert "no such column: bad" in " ".join(model.requests[1].context)
    assert executed[-1][1] == "cfo-1"


def test_sql_agent_reports_unanswerable_without_substituting_metric():
    model = ScriptedModel(json.dumps({"answerable": False, "sql": "", "reason": "No store region attribute exists."}))

    def execute(sql, principal_id):
        raise AssertionError("SQL must not run for unanswerable questions")

    result = SQLAgent(model, lambda question, principal: CONTEXT, execute).run("Revenue by region?", "cfo-1")

    assert result.status == "unanswerable"
    assert result.reason == "No store region attribute exists."


def test_sql_agent_repairs_product_query_that_omits_requested_age_filter():
    model = ScriptedModel(
        json.dumps({"answerable": True, "sql": "SELECT product_id, SUM(quantity) FROM curated_order_items GROUP BY product_id", "assumptions": []}),
        json.dumps({"answerable": True, "sql": "SELECT p.name, SUM(i.quantity) FROM curated_order_items i JOIN curated_orders o ON o.order_id = i.order_id JOIN dim_customer_profiles c ON c.customer_id = o.customer_id JOIN dim_products p ON p.product_id = i.product_id WHERE c.age_group IN ('45-54', '55-64') GROUP BY p.name", "assumptions": []}),
    )
    executed = []

    def execute(sql, principal_id):
        executed.append(sql)
        return {"sql": sql, "columns": ["name", "units"], "rows": [{"name": "Kettle", "units": 2}]}

    result = SQLAgent(model, lambda question, principal: CONTEXT, execute).run(
        "Which products attract customers in age groups 45-54 and 55-64?", "cfo-1"
    )

    assert result.status == "answered"
    assert len(executed) == 1
    assert "dim_customer_profiles" in executed[0]
    assert "omitted the requested customer age filter" in result.attempts[0]["error"]


def test_sql_agent_fails_after_bounded_attempts():
    model = ScriptedModel("not json", "{}", json.dumps({"answerable": True, "sql": ""}))

    result = SQLAgent(model, lambda question, principal: CONTEXT, lambda sql, principal: {}).run("revenue", "cfo-1")

    assert result.status == "failed"
    assert len(result.attempts) == 3


def test_render_schema_context_includes_joins_rules_and_row_counts():
    rendered = render_schema_context(CONTEXT)

    assert "TABLE dim_categories" in rendered and "rows=0" in rendered
    assert "dim_products.category_id = dim_categories.category_id" in rendered
    assert "Revenue counts only succeeded orders." in rendered
