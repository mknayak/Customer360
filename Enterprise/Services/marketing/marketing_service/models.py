from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


CampaignStatus = Literal["draft", "scheduled", "active", "paused", "ended", "cancelled"]
ChannelType = Literal["email", "sms", "push", "paid_search", "social", "direct_mail", "in_store", "web"]


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1)
    objective: str | None = None
    status: CampaignStatus = "draft"
    start_date: datetime = Field(default_factory=utc_now)
    end_date: datetime | None = None
    budget_amount: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    objective: str | None = None
    status: CampaignStatus | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    budget_amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class Campaign(CampaignCreate):
    campaign_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AudienceCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    segment: str | None = None
    criteria: dict[str, str] = Field(default_factory=dict)
    status: str = "active"


class Audience(AudienceCreate):
    audience_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1)
    channel_type: ChannelType
    provider: str | None = None
    status: str = "active"


class Channel(ChannelCreate):
    channel_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)


class CampaignAudienceCreate(BaseModel):
    audience_id: str


class CampaignAudience(CampaignAudienceCreate):
    campaign_id: str
    created_at: datetime = Field(default_factory=utc_now)


class CampaignChannelCreate(BaseModel):
    channel_id: str
    allocation_percent: float = Field(default=0, ge=0, le=100)


class CampaignChannel(CampaignChannelCreate):
    campaign_id: str
    created_at: datetime = Field(default_factory=utc_now)


InteractionType = Literal["sent", "delivered", "opened", "clicked", "converted", "opted_out"]


class CampaignInteractionCreate(BaseModel):
    customer_id: str = Field(min_length=1)
    event_type: InteractionType
    channel_id: str | None = None
    occurred_at: datetime = Field(default_factory=utc_now)
    detail: str | None = None


class CampaignInteraction(CampaignInteractionCreate):
    interaction_id: str = Field(default_factory=lambda: str(uuid4()))
    campaign_id: str
