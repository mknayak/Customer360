from datetime import datetime

from fastapi import FastAPI, Query, status

from .models import Event, EventCreate
from .repository import EventRepository

app = FastAPI(title="Customer360 Event Service", version="0.1.0")
repository = EventRepository()


@app.get("/api/health")
def health() -> dict[str, str]:
    repository.list_events(limit=1)
    return {"status": "ok", "service": "events"}


@app.post("/api/events", response_model=Event, status_code=status.HTTP_201_CREATED)
def append_event(payload: EventCreate) -> Event:
    return repository.append(Event(**payload.model_dump()))


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
    event_type: str | None = Query(default=None),
    source_service: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[Event]:
    return repository.list_events(
        event_type=event_type,
        source_service=source_service,
        recorded_after=recorded_after,
        limit=limit,
    )
