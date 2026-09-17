from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventCreate(BaseModel):
    source_service: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    aggregate_type: str = Field(min_length=1)
    aggregate_id: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)
    correlation_id: str | None = None
    causation_id: str | None = None
    schema_version: int = Field(default=1, ge=1)


class Event(EventCreate):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    recorded_at: datetime = Field(default_factory=utc_now)
