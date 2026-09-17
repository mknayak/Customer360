from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SiteCreate(BaseModel):
    name: str = Field(min_length=1)
    type: str = Field(pattern="^(STORE|WEBSITE|MOBILE_APP)$")
    city: str | None = None
    country: str | None = None
    opened_date: datetime | None = None
    status: str = "active"


class SiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    type: str | None = Field(default=None, pattern="^(STORE|WEBSITE|MOBILE_APP)$")
    city: str | None = None
    country: str | None = None
    opened_date: datetime | None = None
    status: str | None = None


class Site(SiteCreate):
    site_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class VisitCreate(BaseModel):
    customer_id: str = Field(min_length=1)
    site_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    started_at: datetime | None = None
    ended_at: datetime | None = None


class Visit(VisitCreate):
    visit_id: str = Field(default_factory=lambda: str(uuid4()))
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None
