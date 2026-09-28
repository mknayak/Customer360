import sys
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "Agent" / "DecisionOS" / "runtime"))
sys.path.insert(0, str(ROOT))

from Agent.app.main import app, resolve_metric, select_metric_with_model, format_trend_answer  # noqa: E402
from Agent.DecisionOS.runtime.decision_os.model_provider import DeterministicModelProvider, ModelResponse, OpenAICompatibleModelProvider  # noqa: E402


def test_health_ok():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ui_route_renders_prompt_box():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    html = response.text.lower()
    assert "customer360" in html
    assert "prompt" in html
    assert "graph-load" in html
    assert "graph-search" in html
    assert "executive data view" in html
    assert "sql-grid" in html


def test_chat_endpoint_runs_investigation_from_prompt():
    client = TestClient(app)
    response = client.post(
        "/api/agent/chat",
        json={"prompt": "Why did revenue fall?", "principal_id": "cfo-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"running", "completed", "validating"}
    assert body["answer"]
    assert body["investigation_id"]


def test_executive_brief_exposes_traceable_decision_sections():
    client = TestClient(app)
    response = client.post(
        "/api/executive/brief",
        json={"prompt": "Which KPI needs attention?", "principal_id": "cfo-1", "executive_role": "CEO"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["question"] == "Which KPI needs attention?"
    assert body["facts"]
    assert body["metrics"][0]["label"] == "Revenue"
    assert body["evidence"][0]["source"] in {"analytics.query", "data-platform:/api/kpis/revenue"}
    assert body["follow_up_questions"]
    assert body["conversation_id"]
    assert body["executive_role"] == "CEO"
    history = client.get(f"/api/conversations/{body['conversation_id']}")
    assert history.status_code == 200
    assert history.json()["messages"]


def test_executive_brief_selects_metric_from_question():
    response = TestClient(app).post(
        "/api/executive/brief",
        json={"prompt": "What is the cart abandonment rate?", "principal_id": "cfo-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"][0]["label"] == "Cart abandonment"
    assert body["evidence"][0]["query"]["metric"] == "cart_abandonment"


def test_executive_brief_counts_payment_failures():
    response = TestClient(app).post(
        "/api/executive/brief",
        json={"prompt": "How many times payment failed?", "principal_id": "cfo-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"][0]["label"] == "Payment failures"
    assert body["evidence"][0]["query"]["metric"] == "payment_failures"
    assert "payment failures" in body["answer"].lower()


def test_metric_resolver_maps_average_cart_value():
    assert resolve_metric("avg cart value") == ("average_cart_value", "Average cart value", "USD")


def test_deterministic_planner_selects_orders_join_for_customer_product_analysis(monkeypatch):
    monkeypatch.setattr("Agent.app.main.model_provider", DeterministicModelProvider())

    selection, model, query = select_metric_with_model("Which customers bought which products?")

    assert selection[0] == "product_performance"
    assert model == "deterministic"
    assert query["joins"] == ["orders"]
    assert query["dimensions"] == ["customer", "product"]


def test_deterministic_planner_groups_payment_failures_by_customer(monkeypatch):
    monkeypatch.setattr("Agent.app.main.model_provider", DeterministicModelProvider())

    selection, model, query = select_metric_with_model("How do payment failures vary by customer?")

    assert selection[0] == "payment_failures"
    assert model == "deterministic"
    assert query == {"profile_dimension": "country"}
    assert select_metric_with_model("Payment failures by age group")[2] == {"profile_dimension": "age_group"}


def test_payment_failure_customer_question_returns_aggregate_comparison(monkeypatch):
    from Agent.app import main
    from Agent.DecisionOS.runtime.decision_os.tools import ToolExecution

    monkeypatch.setattr(main, "model_provider", DeterministicModelProvider())

    def grouped_result(inputs):
        assert inputs["metric"] == "payment_failures"
        assert inputs["profile_dimension"] in {"country", "age_group"}
        rows = [{"group": "US", "value": 9}, {"group": "GB", "value": 4}] if inputs["profile_dimension"] == "country" else []
        return ToolExecution(
            data={"value": rows, "definition": "PaymentFailed events by current CRM profile", "unmatched_events": 2, "suppressed_groups": 1},
            source=("data-platform:/api/payment-failures/by-profile",),
            query_metadata={"metric": "payment_failures", "profile_dimension": inputs["profile_dimension"], "live": True},
            evidence_references=("analytics:payment_failures",),
        )

    dispatcher = main.engine._tools
    monkeypatch.setitem(dispatcher._tools, "analytics.query", replace(dispatcher._tools["analytics.query"], handler=grouped_result))
    client = TestClient(app)
    response = client.post("/api/executive/brief", json={"prompt": "How do payment failures vary by customer?", "principal_id": "cfo-1"})

    assert response.status_code == 200
    body = response.json()
    assert "US (9 events)" in body["answer"]
    assert "GB (4 events)" in body["answer"]
    assert body["profile_breakdown"]["rows"] == [{"group": "US", "value": 9}, {"group": "GB", "value": 4}]
    assert body["evidence"][0]["query"]["profile_dimension"] == "country"
    assert "not payment failure rates" in body["limitations"][0]

    sparse = client.post("/api/executive/brief", json={"prompt": "How do payment failures vary by customer?", "principal_id": "cfo-1", "profile_dimension": "age_group"}).json()
    assert sparse["profile_breakdown"]["rows"] == []
    assert "No reportable" in sparse["answer"]
    assert any("Fewer than two" in item for item in sparse["limitations"])


def test_llm_planner_returns_semantic_query_ir(monkeypatch):
    provider = OpenAICompatibleModelProvider("https://llm.example", "secret", "test-model")
    provider.complete = lambda request: ModelResponse(
        '{"tool":"analytics.query","query":{"metric":"revenue","dimensions":["period"],"filters":{"payment_status":"succeeded"},"order":"desc","limit":10}}',
        "test",
        "test-model",
    )
    monkeypatch.setattr("Agent.app.main.model_provider", provider)

    selection, model, query = select_metric_with_model("revenue by day")

    assert selection == ("revenue", "Revenue", "USD")
    assert model == "test-model"
    assert query == {"granularity": "day"}


def test_executive_brief_routes_most_dropped_page_to_page_dropoff():
    response = TestClient(app).post(
        "/api/executive/brief",
        json={"prompt": "What is the most dropped page?", "principal_id": "cfo-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"][0]["label"] == "Most dropped page"
    assert body["evidence"][0]["query"]["metric"] == "page_dropoff"


def test_executive_brief_routes_most_visited_page_to_page_popularity():
    response = TestClient(app).post(
        "/api/executive/brief",
        json={"prompt": "What is the most visited page?", "principal_id": "cfo-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"][0]["label"] == "Most visited page"
    assert body["evidence"][0]["query"]["metric"] == "page_popularity"


def test_executive_brief_classifies_customer_retention():
    response = TestClient(app).post(
        "/api/executive/brief",
        json={"prompt": "How is customer retention?", "principal_id": "cfo-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"][0]["label"] == "Customer retention"
    assert body["evidence"][0]["query"]["metric"] == "retention"


def test_retention_period_question_returns_chart_points_and_comparison(monkeypatch):
    from Agent.DecisionOS.runtime.decision_os.tools import ToolExecution

    monkeypatch.setattr("Agent.app.main.model_provider", DeterministicModelProvider())
    def trend_result(inputs):
        assert inputs["metric"] == "retention"
        assert inputs["granularity"] == "month"
        points = [{"period": "2026-01", "value": None, "numerator": 0, "denominator": 0},
                  {"period": "2026-02", "value": 0.5, "numerator": 1, "denominator": 2},
                  {"period": "2026-03", "value": 0.75, "numerator": 3, "denominator": 4}]
        return ToolExecution(data={"value": points, "definition": "Adjacent calendar month cohorts"},
                             source=("data-platform:/api/trends",), query_metadata={"metric": "retention", "granularity": "month", "live": True},
                             evidence_references=("analytics:retention",))
    from Agent.app import main
    dispatcher = main.engine._tools
    monkeypatch.setitem(dispatcher._tools, "analytics.query", replace(dispatcher._tools["analytics.query"], handler=trend_result))

    response = TestClient(app).post("/api/executive/brief", json={"prompt": "How does retention vary by period?", "principal_id": "cfo-1"})
    assert response.status_code == 200
    body = response.json()
    assert "increased" in body["answer"]
    assert "25.00 percentage points" in body["answer"]
    assert body["time_series"]["points"][0]["value"] is None
    assert body["time_series"]["granularity"] == "month"
    assert "repeat-purchase KPI" in body["limitations"][0]


def test_single_period_cannot_establish_trend():
    answer, facts, _ = format_trend_answer("Customer retention", "%", [{"period": "2026-01", "value": 0.5}], "month")
    assert "not enough data" in answer
    assert facts == ["2026-01: 50.00%"]


def test_segment_conversion_does_not_fall_back_to_revenue():
    response = TestClient(app).post(
        "/api/executive/brief",
        json={"prompt": "What segments of users converts to customer?", "principal_id": "cfo-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"][0]["label"] == "Segment conversion"
    assert "segment assignments" in body["answer"]
    assert body["evidence"][0]["query"]["metric"] == "segment_conversion"


def test_product_performance_brief_has_renderable_metric_value():
    response = TestClient(app).post(
        "/api/executive/brief",
        json={"prompt": "What is most selling product?", "principal_id": "cfo-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"][0]["label"] == "Product performance"
    assert isinstance(body["metrics"][0]["value"], (list, int, float))
    assert "[object Object]" not in body["answer"]


def test_llm_configured_brief_answers_through_sql_agent(monkeypatch):
    from Agent.app import main
    from Agent.DecisionOS.runtime.decision_os.tools import ToolExecution

    provider = OpenAICompatibleModelProvider("https://llm.example", "secret", "test-model")
    provider.complete = lambda request: ModelResponse("Kitchen leads revenue with $20.00 (50%) [sql:q-1].", "test", "test-model")
    monkeypatch.setattr(main, "model_provider", provider)

    def sql_result(inputs):
        assert inputs == {"question": "Which category contributes most revenue?", "principal_id": "cfo-1"}
        data = {"status": "answered", "question": inputs["question"], "sql": "SELECT category, revenue FROM x", "columns": ["category", "revenue"],
                "rows": [{"category": "Kitchen", "revenue": 20.0}, {"category": "Uncategorized", "revenue": 20.0}], "assumptions": ("Products without a category are Uncategorized",),
                "reason": "", "attempts": [{"attempt": 1, "sql": "SELECT category, revenue FROM x", "error": None}], "context_tables": ["dim_categories"],
                "business_rules": ["Revenue counts only succeeded orders."], "execution": {"query_id": "q-1", "tables": ["dim_categories"], "truncated": False}}
        return ToolExecution(data=data, source=("data-platform:/api/sql/execute",), query_metadata={"tool": "analytics.sql", "live": True}, evidence_references=("sql:q-1",))

    dispatcher = main.engine._tools
    monkeypatch.setitem(dispatcher._tools, "analytics.sql", replace(dispatcher._tools["analytics.sql"], handler=sql_result))

    body = TestClient(app).post("/api/executive/brief", json={"prompt": "Which category contributes most revenue?", "principal_id": "cfo-1"}).json()

    assert body["answer"].startswith("Kitchen leads revenue")
    assert body["sql_result"]["rows"][0]["category"] == "Kitchen"
    assert body["evidence"][0]["id"] == "sql:q-1"
    assert "Products without a category are Uncategorized" in body["limitations"]
    assert any(step["title"] == "Retrieved schema context" for step in body["thinking_steps"])


def test_sql_agent_is_not_used_for_trend_questions_or_without_llm(monkeypatch):
    from Agent.app import main

    monkeypatch.setattr(main, "model_provider", DeterministicModelProvider())
    assert not main.use_sql_agent("Which category contributes most revenue?", None, None)
    monkeypatch.setattr(main, "model_provider", OpenAICompatibleModelProvider("https://llm.example", "secret", "test-model"))
    assert main.use_sql_agent("Which category contributes most revenue?", None, None)
    assert not main.use_sql_agent("How does revenue trend by month?", None, None)
    assert not main.use_sql_agent("Which customer country has most payment failures?", None, None)


def test_create_and_run_investigation():
    client = TestClient(app)
    response = client.post(
        "/api/investigations",
        json={"question": "Why did revenue fall?", "principal_id": "cfo-1"},
    )
    assert response.status_code == 200
    investigation_id = response.json()["investigation_id"]

    run_response = client.post(f"/api/investigations/{investigation_id}/run")
    assert run_response.status_code == 200
    body = run_response.json()
    assert body["status"] in {"running", "completed", "validating"}
    assert "tool_results" in body


def test_semantic_lookup_endpoint_returns_governed_definition():
    response = TestClient(app).post("/api/semantic/lookup", json={"term": "conversion rate"})

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "resolved"
    assert body["evidence_references"] == ["metric-definition:customer360.conversion"]


def test_graph_sync_and_path_endpoint():
    client = TestClient(app)
    response = client.post(
        "/api/graph/sync",
        json={
            "entities": [
                {"entity_type": "customer", "entity_id": "customer-test"},
                {"entity_type": "order", "entity_id": "order-test"},
            ],
            "relationships": [
                {"from_type": "customer", "from_id": "customer-test", "relationship_type": "customer_order", "to_type": "order", "to_id": "order-test"}
            ],
        },
    )

    assert response.status_code == 200
    path = client.get("/api/graph/paths?from_id=customer-test&to_id=order-test")
    assert path.status_code == 200
    assert path.json()["data"]["found"] is True


def test_graph_neighbors_and_search_endpoints_support_ui_explorer():
    client = TestClient(app)
    client.post("/api/graph/sync", json={"entities": [{"entity_type": "customer", "entity_id": "customer-ui"}, {"entity_type": "product", "entity_id": "product-ui"}], "relationships": [{"from_type": "customer", "from_id": "customer-ui", "relationship_type": "customer_order", "to_type": "product", "to_id": "product-ui"}]})
    neighbors = client.get("/api/graph/neighbors?entity_type=customer&entity_id=customer-ui")
    assert neighbors.status_code == 200
    assert neighbors.json()["data"]["neighbors"][0]["entity_id"] == "product-ui"
    search = client.post("/api/graph/search", json={"query": "customer-ui"})
    assert search.status_code == 200
    assert search.json()["data"]["entities"][0]["entity_id"] == "customer-ui"


def test_rag_ingestion_search_and_authorization():
    client = TestClient(app)
    ingest = client.post(
        "/api/rag/documents",
        json={
            "document_id": "brief-agent-test",
            "title": "Product launch brief",
            "content": "Trail shoe launch notes for gold customers and the spring campaign.",
            "source": "marketing:briefs",
            "document_type": "brief",
            "authorized_principals": ["executive"],
        },
    )
    assert ingest.status_code == 200
    assert ingest.json()["chunks"] == 1

    unauthorized = client.post(
        "/api/rag/search",
        json={"query": "trail shoe launch", "principal_id": "analyst"},
    )
    assert unauthorized.status_code == 200
    assert unauthorized.json()["data"]["passages"] == []

    result = client.post(
        "/api/rag/search",
        json={"query": "trail shoe launch", "principal_id": "executive"},
    )
    assert result.status_code == 200
    assert result.json()["data"]["passages"][0]["document_id"] == "brief-agent-test"
    assert result.json()["evidence_references"][0].startswith("document-chunk:")


def test_rag_answer_returns_citations_and_model_status():
    client = TestClient(app)
    client.post("/api/rag/documents", json={"document_id": "rag-answer-test", "title": "Finance policy", "content": "Revenue recognition requires approved order evidence.", "source": "finance:policy", "authorized_principals": ["cfo-1"]})
    answer = client.post("/api/rag/answer", json={"query": "approved order evidence", "principal_id": "cfo-1"})
    assert answer.status_code == 200
    assert answer.json()["passages"]
    assert answer.json()["evidence_references"]
    assert client.get("/api/agent/model-status").status_code == 200


def test_governed_investigation_routes_agents_and_builds_decision_record():
    response = TestClient(app).post(
        "/api/agent/investigate",
        json={"prompt": "Why did revenue fall?", "principal_id": "cfo-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "finance-intelligence" in body["plan"]["agents"]
    assert body["decision_record"]["evidence"]
    assert body["decision_record"]["status"] in {"validated", "blocked"}


def test_investigation_permission_is_fail_closed():
    response = TestClient(app).post(
        "/api/agent/investigate",
        json={"prompt": "Why did revenue fall?", "principal_id": "unknown-principal"},
    )

    assert response.status_code == 403
