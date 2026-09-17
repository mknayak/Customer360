from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


FeedbackSource = Literal["web", "mobile", "store", "support", "survey", "social"]
Sentiment = Literal["positive", "neutral", "negative", "mixed", "unknown"]


class FeedbackCreate(BaseModel):
    customer_id: str = Field(min_length=1)
    source: FeedbackSource
    rating: int = Field(ge=1, le=5)
    comment: str | None = None
    product_id: str | None = None
    order_id: str | None = None
    campaign_id: str | None = None
    site_id: str | None = None
    sentiment: Sentiment = "unknown"
    status: str = "submitted"


class FeedbackUpdate(BaseModel):
    source: FeedbackSource | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = None
    product_id: str | None = None
    order_id: str | None = None
    campaign_id: str | None = None
    site_id: str | None = None
    sentiment: Sentiment | None = None
    status: str | None = Field(default=None, min_length=1)


class Feedback(FeedbackCreate):
    feedback_id: str = Field(default_factory=lambda: str(uuid4()))
    submitted_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
