"""HTTP API for raw ingestion and governed KPI queries."""

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .warehouse import EventWarehouse


class EventBatch(BaseModel):
    events: list[dict[str, Any]] = Field(min_length=1, max_length=10_000)


app = FastAPI(title="Customer360 Data Platform", version="0.1.0")
warehouse = EventWarehouse()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "data-platform"}


@app.post("/api/ingest/events")
def ingest_events(batch: EventBatch) -> dict[str, int]:
    return warehouse.ingest(batch.events)


@app.post("/api/ingest/event-service")
def ingest_event_service(origin: str | None = None, limit: int = Query(default=1000, ge=1, le=10_000)) -> dict[str, int]:
    try:
        return warehouse.ingest_event_service(origin or os.getenv("EVENTS_ORIGIN", "http://127.0.0.1:8007"), limit=limit)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Event ingestion failed: {error}") from error


@app.get("/api/kpis/{metric}")
def get_kpi(metric: str) -> dict[str, Any]:
    try:
        return warehouse.kpi(metric)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error