from fastapi.testclient import TestClient

from data_platform import app as app_module
from data_platform.semantic_query import SemanticQueryIR, SemanticQueryPlanner
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


def test_planner_compiles_and_executes_allowlisted_page_dropoff_query(tmp_path):
    planner = SemanticQueryPlanner()
    warehouse = _warehouse(tmp_path)
    compiled = planner.plan(SemanticQueryIR("page_dropoff", limit=10), "cfo-1")
    result = warehouse.execute_semantic(compiled)

    assert result["rows"] == [{"page": "products", "exits": 2}, {"page": "about", "exits": 1}]
    assert "event_type = 'Exit'" in result["query"]["sql"]
    assert result["lineage"] == ("Exit", "curated_content_activity")
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
