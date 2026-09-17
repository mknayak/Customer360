from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class JourneyItem(BaseModel):
    product_id: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    unit_price: float = Field(gt=0)


class ShoppingJourneyCreate(BaseModel):
    customer_id: str = Field(min_length=1)
    site_id: str = Field(min_length=1)
    store_id: str | None = None
    delivery_mode: Literal["email", "postal", "collection", "collect_at_store"] = "collect_at_store"
    items: list[JourneyItem] = Field(min_length=1)
    correlation_id: str | None = None


class WorkflowResult(BaseModel):
    workflow_id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_type: str = "shopping_journey"
    status: Literal["completed", "failed"]
    correlation_id: str
    visit_id: str | None = None
    cart_id: str | None = None
    published_event_ids: list[str] = Field(default_factory=list)
    failure: str | None = None


class ServiceResponse(BaseModel):
    data: dict[str, Any]
