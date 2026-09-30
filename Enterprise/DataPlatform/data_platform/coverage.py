"""Coverage inventory for service events, warehouse models, and semantic metrics."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from .semantic_query import SemanticCatalog

try:
    from Enterprise.Services.events.event_service.contracts import EVENT_CONTRACTS
except ModuleNotFoundError:
    from event_service.contracts import EVENT_CONTRACTS


CURATED_EVENTS = frozenset({
    "VisitStarted",
    "CartCreated",
    "CartAbandoned",
    "CartItemAdded",
    "CartItemUpdated",
    "CartItemRemoved",
    "OrderCreated",
    "ProductCreated",
    "ProductUpdated",
    "CategoryCreated",
    "PageVisit",
    "ContentView",
    "Search",
    "TimeOnPage",
    "Exit",
    "FeedbackSubmitted",
    "FeedbackUpdated",
    "FeedbackDeleted",
})

# These events remain available in raw_events until a curated model is justified.
RAW_ONLY_EVENTS = frozenset({
    "SiteCreated",
    "SiteUpdated",
    "SiteDeleted",
    "VisitEnded",
    "UserLogin",
    "ProductViewed",
    "CheckoutStarted",
    "PaymentFailed",
    "PaymentCompleted",
    "OrderCancelled",
    "OrderStatusChanged",
    "CustomerCreated",
    "CustomerUpdated",
    "CustomerDeleted",
    "CustomersImported",
    "PriceChanged",
    "PromotionCreated",
    "PromotionStarted",
    "PromotionEnded",
    "CatalogImported",
    "CampaignCreated",
    "CampaignStarted",
    "CampaignEnded",
    "CampaignAudienceChanged",
    "CampaignInteractionRecorded",
    "CampaignsImported",
    "AudienceCreated",
    "ChannelCreated",
    "CampaignAudienceAssigned",
    "CampaignChannelAssigned",
    "WorkflowStarted",
    "WorkflowCompleted",
    "WorkflowFailed",
})


@dataclass(frozen=True)
class EventCoverage:
    source: str
    event_type: str
    disposition: str


def registered_event_types() -> frozenset[str]:
    return frozenset(event_type for events in EVENT_CONTRACTS.values() for event_type in events)


def event_coverage() -> tuple[EventCoverage, ...]:
    decisions = {event_type: "curated" for event_type in CURATED_EVENTS}
    decisions.update({event_type: "raw_only" for event_type in RAW_ONLY_EVENTS})
    return tuple(
        EventCoverage(source, event_type, decisions[event_type])
        for source, events in sorted(EVENT_CONTRACTS.items())
        for event_type in events
    )


def validate_event_coverage() -> None:
    registered = registered_event_types()
    decided = CURATED_EVENTS | RAW_ONLY_EVENTS
    missing = registered - decided
    unknown = decided - registered
    overlap = CURATED_EVENTS & RAW_ONLY_EVENTS
    if missing or unknown or overlap:
        raise AssertionError(
            f"Invalid event coverage: missing={sorted(missing)}, "
            f"unknown={sorted(unknown)}, overlap={sorted(overlap)}"
        )


def warehouse_tables(connection: sqlite3.Connection) -> frozenset[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return frozenset(row[0] for row in rows)


def validate_metric_coverage(connection: sqlite3.Connection, catalog: SemanticCatalog | None = None) -> None:
    available = warehouse_tables(connection)
    missing = {
        metric.metric_id: metric.model
        for metric in (catalog or SemanticCatalog()).metrics()
        if metric.model not in available
    }
    if missing:
        raise AssertionError(f"Metrics reference missing warehouse tables: {missing}")


def coverage_snapshot(connection: sqlite3.Connection, catalog: SemanticCatalog | None = None) -> dict[str, Any]:
    validate_event_coverage()
    validate_metric_coverage(connection, catalog)
    return {
        "events": [item.__dict__ for item in event_coverage()],
        "warehouse_tables": sorted(warehouse_tables(connection)),
        "metrics": [
            {
                "metric": metric.metric_id,
                "model": metric.model,
                "dimensions": sorted(metric.dimensions),
                "lineage": metric.lineage,
            }
            for metric in (catalog or SemanticCatalog()).metrics()
        ],
    }
