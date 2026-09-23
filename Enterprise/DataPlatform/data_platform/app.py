"""HTTP API for raw ingestion and governed KPI queries."""

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .warehouse import EventWarehouse
from .semantic_query import SemanticQueryIR, SemanticQueryPlanner


class EventBatch(BaseModel):
    events: list[dict[str, Any]] = Field(min_length=1, max_length=10_000)


class SemanticContextRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    limit: int = Field(default=5, ge=1, le=20)


class SemanticQueryRequest(BaseModel):
    principal_id: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    dimensions: tuple[str, ...] = ()
    filters: dict[str, Any] = Field(default_factory=dict)
    order: str = "desc"
    limit: int = Field(default=25, ge=1, le=1000)


app = FastAPI(title="Customer360 Data Platform", version="0.1.0")
warehouse = EventWarehouse()
semantic_query_planner = SemanticQueryPlanner()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "data-platform"}


@app.post("/api/ingest/events")
def ingest_events(batch: EventBatch) -> dict[str, int]:
    return warehouse.ingest(batch.events)


@app.post("/api/ingest/event-service")
def ingest_event_service(origin: str | None = None, limit: int = Query(default=1000, ge=1, le=1000), max_batches: int = Query(default=100, ge=1, le=1000)) -> dict[str, int]:
    try:
        event_result = warehouse.ingest_event_service(origin or os.getenv("EVENTS_ORIGIN", "http://127.0.0.1:8007"), limit=limit, max_batches=max_batches)
        order_result = warehouse.backfill_shopping_orders(os.getenv("SHOPPING_ORIGIN", "http://127.0.0.1:8003"))
        return {"events_received": event_result["received"], "events_stored": event_result["stored"], "event_batches": event_result["batches"], "orders_received": order_result["received"], "orders_stored": order_result["stored"]}
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Event ingestion failed: {error}") from error


@app.get("/api/kpis/{metric}")
def get_kpi(metric: str) -> dict[str, Any]:
    try:
        return warehouse.kpi(metric)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/quality")
def data_quality() -> dict[str, Any]:
    return warehouse.quality()


@app.get("/api/catalog")
def metric_catalog() -> list[dict[str, Any]]:
    return warehouse.catalog()


@app.post("/api/reconcile")
def reconcile(payload: dict[str, Any]) -> dict[str, Any]:
    return warehouse.reconcile(payload)


@app.post("/api/semantic-query/context")
def semantic_query_context(payload: SemanticContextRequest) -> dict[str, Any]:
    return semantic_query_planner.context(payload.question, payload.limit)


@app.post("/api/semantic-query/execute")
def execute_semantic_query(payload: SemanticQueryRequest) -> dict[str, Any]:
    try:
        query = SemanticQueryIR(payload.metric, payload.dimensions, payload.filters, payload.order, payload.limit)
        compiled = semantic_query_planner.plan(query, payload.principal_id)
        return warehouse.execute_semantic(compiled)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error