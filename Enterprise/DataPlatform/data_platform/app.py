"""HTTP API for raw ingestion and governed KPI queries."""

import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .warehouse import EventWarehouse
from .semantic_query import SemanticQueryIR, SemanticQueryPlanner
from .text_to_sql import SQLValidationError, TextToSQLService
from .coverage import coverage_snapshot


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
    joins: tuple[str, ...] = ()


class TrendRequest(BaseModel):
    principal_id: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    granularity: str = Field(pattern="^(day|week|month)$")


class PaymentFailureProfileRequest(BaseModel):
    principal_id: str = Field(min_length=1)
    dimension: str = Field(pattern="^(country|age_group)$")


class SQLContextRequest(BaseModel):
    principal_id: str = Field(min_length=1)
    question: str = Field(min_length=3, max_length=4000)
    max_tables: int = Field(default=6, ge=1, le=20)


class SQLExecuteRequest(BaseModel):
    principal_id: str = Field(min_length=1)
    sql: str = Field(min_length=6, max_length=20_000)
    limit: int = Field(default=200, ge=1, le=1000)


app = FastAPI(title="Customer360 Data Platform", version="0.1.0")
warehouse = EventWarehouse()
semantic_query_planner = SemanticQueryPlanner()
text_to_sql = TextToSQLService(warehouse.database_path, policy=semantic_query_planner.policy)


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
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Event ingestion failed: {error}") from error
    result = {"events_received": event_result["received"], "events_stored": event_result["stored"], "event_batches": event_result["batches"], "orders_received": order_result["received"], "orders_stored": order_result["stored"]}
    try:
        product_result = warehouse.backfill_product_catalog(os.getenv("PRODUCT_ORIGIN", "http://127.0.0.1:8002"))
        result.update(products=product_result["products"], categories=product_result["categories"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        result["product_catalog_error"] = str(error)
    try:
        customer_result = warehouse.backfill_customer_profiles(os.getenv("CRM_ORIGIN", "http://127.0.0.1:8001"))
        result.update(customer_profiles=customer_result["profiles"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        result["customer_profiles_error"] = str(error)
    text_to_sql.refresh()
    return result


@app.get("/api/kpis/{metric}")
def get_kpi(metric: str) -> dict[str, Any]:
    try:
        return warehouse.kpi(metric)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/trends")
def get_trend(payload: TrendRequest) -> dict[str, Any]:
    try:
        governed_metrics = {"retention": "average_cart_value", "conversion": "visits", "cart_abandonment": "average_cart_value"}
        metric = semantic_query_planner.catalog.get(governed_metrics.get(payload.metric, payload.metric))
        semantic_query_planner.policy.authorize(payload.principal_id, metric)
        return warehouse.trend(payload.metric, payload.granularity)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/payment-failures/by-profile")
def payment_failures_by_profile(payload: PaymentFailureProfileRequest) -> dict[str, Any]:
    try:
        metric = semantic_query_planner.catalog.get("payment_failures")
        semantic_query_planner.policy.authorize(payload.principal_id, metric)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error

    profiles: dict[str, str | None] = {}
    origin = os.getenv("CRM_ORIGIN", "http://127.0.0.1:8001").rstrip("/")
    try:
        for page in range(1, 1001):
            with urlopen(f"{origin}/api/customers?{urlencode({'page': page, 'page_size': 100})}", timeout=10) as response:
                directory = json.loads(response.read())
            for customer in directory["items"]:
                profiles[customer["customer_id"]] = customer.get(payload.dimension)
            if page >= directory["total_pages"]:
                break
        else:
            raise ValueError("CRM customer directory exceeds supported pagination limit")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=502, detail="CRM customer profiles unavailable or incomplete") from error
    return warehouse.payment_failures_by_profile(payload.dimension, profiles)


@app.get("/api/quality")
def data_quality() -> dict[str, Any]:
    return warehouse.quality()


@app.get("/api/catalog")
def metric_catalog() -> list[dict[str, Any]]:
    return warehouse.catalog()


@app.get("/api/coverage")
def coverage() -> dict[str, Any]:
    return coverage_snapshot(warehouse.connection, semantic_query_planner.catalog)


@app.post("/api/reconcile")
def reconcile(payload: dict[str, Any]) -> dict[str, Any]:
    return warehouse.reconcile(payload)


@app.post("/api/semantic-query/context")
def semantic_query_context(payload: SemanticContextRequest) -> dict[str, Any]:
    return semantic_query_planner.context(payload.question, payload.limit)


@app.post("/api/sql/index/refresh")
def refresh_sql_index() -> dict[str, Any]:
    return text_to_sql.refresh()


@app.post("/api/sql/context")
def sql_context(payload: SQLContextRequest) -> dict[str, Any]:
    try:
        return text_to_sql.context(payload.question, payload.principal_id, payload.max_tables)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/sql/execute")
def sql_execute(payload: SQLExecuteRequest) -> dict[str, Any]:
    try:
        return text_to_sql.execute(payload.sql, payload.principal_id, payload.limit)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except SQLValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/semantic-query/execute")
def execute_semantic_query(payload: SemanticQueryRequest) -> dict[str, Any]:
    try:
        query = SemanticQueryIR(payload.metric, payload.dimensions, payload.filters, payload.order, payload.limit, payload.joins)
        compiled = semantic_query_planner.plan(query, payload.principal_id)
        return warehouse.execute_semantic(compiled)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error