from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, status

from .contracts import EVENT_CONTRACTS, validate_event_contract
from .models import Event, EventCreate
from pydantic import BaseModel, Field


class EventBatch(BaseModel):
    events: list[EventCreate] = Field(min_length=1, max_length=10_000)
from .repository import EventRepository

app = FastAPI(title="Customer360 Event Service", version="0.1.0")
repository = EventRepository()


@app.get("/api/health")
def health() -> dict[str, str]:
    repository.list_events(limit=1)
    return {"status": "ok", "service": "events"}


@app.post("/api/events", response_model=Event, status_code=status.HTTP_201_CREATED)
def append_event(payload: EventCreate) -> Event:
    try:
        validate_event_contract(payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return repository.append(Event(**payload.model_dump()))


@app.post("/api/events/batch", response_model=list[Event], status_code=status.HTTP_201_CREATED)
def append_event_batch(batch: EventBatch) -> list[Event]:
    events = []
    for payload in batch.events:
        try:
            validate_event_contract(payload.model_dump())
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        events.append(repository.append(Event(**payload.model_dump())))
    return events


@app.get("/api/contracts")
def event_contracts() -> dict[str, tuple[str, ...]]:
    return EVENT_CONTRACTS


@app.get("/api/events", response_model=list[Event])
def list_events(
    event_type: str | None = Query(default=None),
    source_service: str | None = Query(default=None),
    correlation_id: str | None = Query(default=None),
    recorded_after: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[Event]:
    return repository.list_events(
        event_type=event_type,
        source_service=source_service,
        correlation_id=correlation_id,
        recorded_after=recorded_after,
        limit=limit,
    )


@app.get("/api/events/replay", response_model=list[Event])
def replay_events(
    recorded_after: datetime | None = Query(default=None),
    after_event_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    source_service: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[Event]:
    if after_event_id:
        cursor = next((event for event in repository.list_events(limit=10_000) if event.event_id == after_event_id), None)
        if cursor:
            recorded_after = cursor.recorded_at
    return repository.list_events(
        event_type=event_type,
        source_service=source_service,
        recorded_after=recorded_after,
        limit=limit,
    )
