import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "Agent" / "DecisionOS" / "runtime"))
sys.path.insert(0, str(ROOT))

from Agent.app.main import app  # noqa: E402


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
