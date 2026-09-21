"""Local event contract registry and validation rules."""

from __future__ import annotations

from typing import Any, Mapping


EVENT_CONTRACTS: dict[str, tuple[str, ...]] = {
    "site": ("SiteCreated", "VisitStarted", "VisitEnded"),
    "content-site": ("PageVisit", "ContentView", "Search", "TimeOnPage", "Exit", "UserLogin", "ProductViewed", "CartCreated", "CheckoutStarted", "PaymentFailed", "OrderCreated"),
    "shopping": ("CartCreated", "CartItemAdded", "CartItemUpdated", "CartItemRemoved", "CartAbandoned", "OrderCreated", "PaymentCompleted", "PaymentFailed", "OrderCancelled", "OrderStatusChanged"),
    "crm": ("CustomerCreated", "CustomerUpdated", "CustomerDeleted", "CustomersImported"),
    "product": ("ProductCreated", "ProductUpdated", "PriceChanged", "PromotionCreated", "PromotionStarted", "PromotionEnded", "CatalogImported"),
    "feedback": ("FeedbackSubmitted", "FeedbackUpdated"),
    "marketing": ("CampaignCreated", "CampaignStarted", "CampaignEnded", "CampaignAudienceChanged", "CampaignInteractionRecorded", "CampaignsImported"),
    "orchestration": ("WorkflowStarted", "WorkflowCompleted", "WorkflowFailed"),
}


def validate_event_contract(event: Mapping[str, Any]) -> None:
    source = str(event.get("source_service", ""))
    event_type = str(event.get("event_type", ""))
    if source not in EVENT_CONTRACTS:
        raise ValueError(f"unknown source service: {source}")
    if event_type not in EVENT_CONTRACTS[source]:
        raise ValueError(f"event type {event_type} is not registered for {source}")
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
