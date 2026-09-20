from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, status

from .models import Audience, AudienceCreate, Campaign, CampaignAudience, CampaignAudienceCreate, CampaignChannel, CampaignChannelCreate, CampaignCreate, CampaignInteraction, CampaignInteractionCreate, CampaignUpdate, Channel, ChannelCreate
from .events import publish_event
from .repository import MarketingRepository


app = FastAPI(title="Customer360 Marketing Service", version="0.1.0")
repository = MarketingRepository()


def validate_campaign_dates(item: Campaign) -> None:
    if item.end_date is not None and item.end_date < item.start_date:
        raise HTTPException(status_code=400, detail="end_date cannot be before start_date")


def get_campaign_or_404(campaign_id: str) -> Campaign:
    item = repository.get_campaign(campaign_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return item


def get_audience_or_404(audience_id: str) -> Audience:
    item = repository.get_audience(audience_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Audience not found")
    return item


def get_channel_or_404(channel_id: str) -> Channel:
    item = repository.get_channel(channel_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return item


@app.get("/api/health")
def health() -> dict[str, str]:
    repository.list_campaigns()
    return {"status": "ok", "service": "marketing"}


@app.post("/api/campaigns", response_model=Campaign, status_code=status.HTTP_201_CREATED)
def create_campaign(payload: CampaignCreate) -> Campaign:
    item = Campaign(**payload.model_dump())
    validate_campaign_dates(item)
    item = repository.save_campaign(item)
    publish_event("CampaignCreated", "campaign", item.campaign_id, item.model_dump(mode="json"), occurred_at=item.created_at)
    return item


@app.get("/api/campaigns", response_model=list[Campaign])
def list_campaigns(status: str | None = None) -> list[Campaign]:
    return repository.list_campaigns(status=status)


@app.get("/api/campaigns/{campaign_id}", response_model=Campaign)
def get_campaign(campaign_id: str) -> Campaign:
    return get_campaign_or_404(campaign_id)


@app.put("/api/campaigns/{campaign_id}", response_model=Campaign)
def update_campaign(campaign_id: str, payload: CampaignUpdate) -> Campaign:
    item = get_campaign_or_404(campaign_id)
    changes = payload.model_dump(exclude_unset=True)
    updated = item.model_copy(update={**changes, "updated_at": datetime.now(timezone.utc)})
    validate_campaign_dates(updated)
    updated = repository.save_campaign(updated)
    event_type = {"active": "CampaignStarted", "ended": "CampaignEnded"}.get(updated.status, "CampaignUpdated")
    publish_event(event_type, "campaign", updated.campaign_id, updated.model_dump(mode="json"), occurred_at=updated.updated_at)
    return updated


@app.delete("/api/campaigns/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: str) -> None:
    item = get_campaign_or_404(campaign_id)
    repository.delete_campaign(campaign_id)
    publish_event("CampaignDeleted", "campaign", item.campaign_id, {"campaign_id": item.campaign_id}, occurred_at=datetime.now(timezone.utc))


@app.post("/api/audiences", response_model=Audience, status_code=201)
def create_audience(payload: AudienceCreate) -> Audience:
    item = repository.save_audience(Audience(**payload.model_dump()))
    publish_event("AudienceCreated", "audience", item.audience_id, item.model_dump(mode="json"), occurred_at=item.created_at)
    return item


@app.get("/api/audiences", response_model=list[Audience])
def list_audiences() -> list[Audience]:
    return repository.list_audiences()


@app.get("/api/audiences/{audience_id}", response_model=Audience)
def get_audience(audience_id: str) -> Audience:
    return get_audience_or_404(audience_id)


@app.post("/api/channels", response_model=Channel, status_code=201)
def create_channel(payload: ChannelCreate) -> Channel:
    item = repository.save_channel(Channel(**payload.model_dump()))
    publish_event("ChannelCreated", "channel", item.channel_id, item.model_dump(mode="json"), occurred_at=item.created_at)
    return item


@app.get("/api/channels", response_model=list[Channel])
def list_channels() -> list[Channel]:
    return repository.list_channels()


@app.get("/api/channels/{channel_id}", response_model=Channel)
def get_channel(channel_id: str) -> Channel:
    return get_channel_or_404(channel_id)


@app.post("/api/campaigns/{campaign_id}/audiences", response_model=CampaignAudience, status_code=201)
def add_campaign_audience(campaign_id: str, payload: CampaignAudienceCreate) -> CampaignAudience:
    get_campaign_or_404(campaign_id)
    get_audience_or_404(payload.audience_id)
    item = repository.save_campaign_audience(CampaignAudience(campaign_id=campaign_id, **payload.model_dump()))
    publish_event("CampaignAudienceAssigned", "campaign", campaign_id, item.model_dump(mode="json"), occurred_at=item.created_at)
    return item


@app.get("/api/campaigns/{campaign_id}/audiences", response_model=list[Audience])
def list_campaign_audiences(campaign_id: str) -> list[Audience]:
    get_campaign_or_404(campaign_id)
    return repository.list_campaign_audiences(campaign_id)


@app.post("/api/campaigns/{campaign_id}/channels", response_model=CampaignChannel, status_code=201)
def add_campaign_channel(campaign_id: str, payload: CampaignChannelCreate) -> CampaignChannel:
    get_campaign_or_404(campaign_id)
    get_channel_or_404(payload.channel_id)
    item = repository.save_campaign_channel(CampaignChannel(campaign_id=campaign_id, **payload.model_dump()))
    publish_event("CampaignChannelAssigned", "campaign", campaign_id, item.model_dump(mode="json"), occurred_at=item.created_at)
    return item


@app.get("/api/campaigns/{campaign_id}/channels", response_model=list[CampaignChannel])
def list_campaign_channels(campaign_id: str) -> list[CampaignChannel]:
    get_campaign_or_404(campaign_id)
    return repository.list_campaign_channels(campaign_id)


@app.post("/api/campaigns/{campaign_id}/interactions", response_model=CampaignInteraction, status_code=201)
def add_campaign_interaction(campaign_id: str, payload: CampaignInteractionCreate) -> CampaignInteraction:
    get_campaign_or_404(campaign_id)
    if payload.channel_id is not None:
        get_channel_or_404(payload.channel_id)
    item = repository.add_campaign_interaction(CampaignInteraction(campaign_id=campaign_id, **payload.model_dump()))
    publish_event("CampaignInteractionRecorded", "campaign", campaign_id, item.model_dump(mode="json"), occurred_at=item.occurred_at)
    return item


@app.get("/api/campaigns/{campaign_id}/interactions", response_model=list[CampaignInteraction])
def list_campaign_interactions(campaign_id: str, customer_id: str | None = None) -> list[CampaignInteraction]:
    get_campaign_or_404(campaign_id)
    return repository.list_campaign_interactions(campaign_id=campaign_id, customer_id=customer_id)


@app.get("/api/interactions", response_model=list[CampaignInteraction])
def list_interactions(customer_id: str | None = None) -> list[CampaignInteraction]:
    return repository.list_campaign_interactions(customer_id=customer_id)
