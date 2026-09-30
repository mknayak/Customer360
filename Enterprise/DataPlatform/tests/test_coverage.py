from data_platform.coverage import (
    CURATED_EVENTS,
    RAW_ONLY_EVENTS,
    coverage_snapshot,
    event_coverage,
    registered_event_types,
    validate_event_coverage,
    validate_metric_coverage,
)
from data_platform.app import app
from data_platform.warehouse import EventWarehouse
from fastapi.testclient import TestClient


def test_every_registered_event_has_one_explicit_warehouse_disposition():
    validate_event_coverage()

    covered = {(item.source, item.event_type) for item in event_coverage()}
    assert {item.event_type for item in event_coverage()} == set(registered_event_types())
    assert CURATED_EVENTS.isdisjoint(RAW_ONLY_EVENTS)
    assert all(item.disposition in {"curated", "raw_only"} for item in event_coverage())
    assert len(covered) == len(event_coverage())


def test_all_semantic_metrics_reference_existing_warehouse_tables(tmp_path):
    warehouse = EventWarehouse(tmp_path / "analytics.sqlite3")

    validate_metric_coverage(warehouse.connection)
    snapshot = coverage_snapshot(warehouse.connection)

    assert len(snapshot["events"]) == len(event_coverage())
    assert {item["metric"] for item in snapshot["metrics"]}
    assert "curated_feedback" in snapshot["warehouse_tables"]
    warehouse.close()


def test_coverage_endpoint_exposes_current_inventory():
    response = TestClient(app).get("/api/coverage")

    assert response.status_code == 200
    body = response.json()
    assert body["events"]
    assert "curated_feedback" in body["warehouse_tables"]
    assert any(item["metric"] == "customer_complaints" for item in body["metrics"])
