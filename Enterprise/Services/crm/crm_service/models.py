"""CRM API and domain models."""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CustomerCreate(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    phone: str | None = None
    status: str = "active"


class CustomerUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1)
    last_name: str | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, min_length=3)
    phone: str | None = None
    status: str | None = None


class CustomerImport(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    phone: str | None = None
    status: str = "active"
    age_group: str | None = None
    city: str | None = None
    country: str | None = None
    preferred_channel: str | None = None


class Customer(CustomerCreate):
    customer_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CustomerDirectoryItem(Customer):
    age_group: str | None = None
    city: str | None = None
    country: str | None = None
    preferred_channel: str | None = None


class CustomerPage(BaseModel):
    items: list[CustomerDirectoryItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class CustomerProfile(BaseModel):
    customer_id: str
    age_group: str | None = None
    city: str | None = None
    country: str | None = None
    preferred_channel: str | None = None


class CustomerProfileInput(BaseModel):
    age_group: str | None = None
    city: str | None = None
    country: str | None = None
    preferred_channel: str | None = None


class CustomerSegment(BaseModel):
    customer_id: str
    segment: str = Field(min_length=1)
    effective_from: datetime = Field(default_factory=utc_now)
    effective_to: datetime | None = None


class CustomerSegmentInput(BaseModel):
    segment: str = Field(min_length=1)
    effective_from: datetime = Field(default_factory=utc_now)
    effective_to: datetime | None = None