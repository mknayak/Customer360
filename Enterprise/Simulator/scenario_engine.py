"""Deterministic synthetic enterprise scenario generation."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

try:
    from .scenario_ingest import ScenarioIngestor
except ImportError:
    from scenario_ingest import ScenarioIngestor


SCENARIOS = ("normal", "promotion_uplift", "website_degradation", "product_surge", "feedback_spike")


@dataclass(frozen=True)
class ScenarioConfig:
    seed: int = 42
    scenario: str = "normal"
    customers: int = 10_000
    products: int = 100
    sites: int = 5
    journeys: int = 10_000

    def __post_init__(self) -> None:
        if self.scenario not in SCENARIOS:
            raise ValueError(f"scenario must be one of {', '.join(SCENARIOS)}")
        if min(self.customers, self.products, self.sites, self.journeys) < 1:
            raise ValueError("scenario counts must be positive")
        if self.products < 100:
            raise ValueError("products must be at least 100")
        if not 5 <= self.sites <= 10:
            raise ValueError("sites must be between 5 and 10")


class ScenarioGenerator:
    """Generate stable IDs and correlated behavior for a configured scenario."""

    def __init__(self, config: ScenarioConfig) -> None:
        self.config = config
        self.random = random.Random(config.seed)
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def customers(self) -> Iterator[dict[str, Any]]:
        cities = (("London", "GB"), ("Toronto", "CA"), ("Sydney", "AU"), ("New York", "US"), ("Berlin", "DE"))
        for index in range(1, self.config.customers + 1):
            city, country = cities[(index - 1) % len(cities)]
            yield {
                "customer_id": f"customer-{index:06d}",
                "first_name": f"Customer{index:06d}",
                "last_name": "Synthetic",
                "email": f"customer{index:06d}@example.test",
                "phone": None,
                "status": "active",
                "city": city,
                "country": country,
                "preferred_channel": ("email", "mobile", "web")[index % 3],
            }

    def products(self) -> Iterator[dict[str, Any]]:
        categories = ("Home", "Kitchen", "Outdoor", "Personal", "Electronics")
        for index in range(1, self.config.products + 1):
            yield {
                "product_id": f"product-{index:05d}",
                "sku": f"SKU-SY-{index:05d}",
                "name": f"Synthetic Product {index:05d}",
                "description": f"Generated {categories[index % len(categories)].lower()} product",
                "category": categories[index % len(categories)],
                "price_amount": round(15 + (index % 40) * 7.5, 2),
                "currency": "USD",
                "status": "active",
            }

    def sites(self) -> Iterator[dict[str, Any]]:
        cities = ("London", "Toronto", "Sydney", "New York", "Berlin", "Paris", "Tokyo", "Mumbai", "Chicago", "Madrid")
        for index in range(1, self.config.sites + 1):
            yield {
                "site_id": f"site-{index:02d}",
                "name": f"Synthetic Site {index:02d}",
                "type": "WEBSITE" if index == 1 else "STORE",
                "city": cities[index - 1],
                "country": "US" if index == 1 else "GB",
                "status": "active",
            }

    def journeys(self) -> Iterator[dict[str, Any]]:
        products = tuple(self.products())
        sites = tuple(self.sites())
        for index in range(1, self.config.journeys + 1):
            outcome = self._outcome()
            occurred_at = self.start + timedelta(minutes=index)
            customer_id = f"customer-{self.random.randint(1, self.config.customers):06d}"
            site = sites[(index - 1) % len(sites)]
            if self.config.scenario == "product_surge" and self.random.random() < 0.65:
                selected = [products[0]]
            else:
                selected = self.random.sample(products, k=min(1 + self.random.randrange(3), len(products)))
            journey_id = f"journey-{index:07d}"
            yield {
                "journey_id": journey_id,
                "correlation_id": journey_id,
                "customer_id": customer_id,
                "site_id": site["site_id"],
                "occurred_at": occurred_at.isoformat(),
                "outcome": outcome,
                "items": [
                    {"product_id": item["product_id"], "quantity": 1 + self.random.randrange(3), "unit_price": item["price_amount"]}
                    for item in selected
                ],
                "events": self._events(journey_id, customer_id, site["site_id"], outcome, occurred_at, self.config.scenario),
            }

    def dataset(self) -> dict[str, Any]:
        return {
            "metadata": {"seed": self.config.seed, "scenario": self.config.scenario, "generated_at": self.start.isoformat()},
            "customers": list(self.customers()),
            "products": list(self.products()),
            "sites": list(self.sites()),
            "journeys": list(self.journeys()),
        }

    def _outcome(self) -> str:
        weights = {"purchase": 0.28, "abandon": 0.25, "pending": 0.12, "failure": 0.08, "browse": 0.27}
        if self.config.scenario == "promotion_uplift":
            weights["purchase"] += 0.20
            weights["abandon"] -= 0.10
        elif self.config.scenario == "website_degradation":
            weights["failure"] += 0.18
            weights["abandon"] += 0.12
            weights["purchase"] -= 0.15
        elif self.config.scenario == "product_surge":
            weights["purchase"] += 0.08
        elif self.config.scenario == "feedback_spike":
            weights["abandon"] += 0.05
        outcomes, probabilities = zip(*weights.items())
        return self.random.choices(outcomes, weights=probabilities, k=1)[0]

    @staticmethod
    def _events(journey_id: str, customer_id: str, site_id: str, outcome: str, occurred_at: datetime, scenario: str) -> list[dict[str, Any]]:
        events = [{"event_type": "VisitStarted", "aggregate_type": "visit", "aggregate_id": journey_id, "source_service": "site"}]
        if outcome != "browse":
            events.append({"event_type": "CartCreated", "aggregate_type": "cart", "aggregate_id": journey_id, "source_service": "shopping"})
        if outcome == "purchase":
            events.append({"event_type": "OrderCreated", "aggregate_type": "order", "aggregate_id": journey_id, "source_service": "shopping"})
        elif outcome == "abandon":
            events.append({"event_type": "CartAbandoned", "aggregate_type": "cart", "aggregate_id": journey_id, "source_service": "shopping"})
        elif outcome == "failure":
            events.append({"event_type": "PaymentFailed", "aggregate_type": "order", "aggregate_id": journey_id, "source_service": "shopping"})
        if scenario == "feedback_spike":
            events.append({"event_type": "FeedbackSubmitted", "aggregate_type": "feedback", "aggregate_id": journey_id, "source_service": "feedback"})
        previous_event_id = None
        for index, event in enumerate(events, start=1):
            event_id = f"{journey_id}-event-{index:02d}"
            event.update({
                "event_id": event_id,
                "correlation_id": journey_id,
                "causation_id": previous_event_id,
                "payload": {"customer_id": customer_id, "site_id": site_id, "journey_id": journey_id},
                "occurred_at": occurred_at.isoformat(),
                "schema_version": 1,
                "idempotency_key": event_id,
            })
            previous_event_id = event_id
        return events


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a deterministic Customer360 scenario")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--customers", type=int, default=10_000)
    parser.add_argument("--products", type=int, default=100)
    parser.add_argument("--sites", type=int, default=5)
    parser.add_argument("--journeys", type=int, default=10_000)
    parser.add_argument("--ingest", action="store_true", help="push the generated dataset to local enterprise APIs")
    parser.add_argument("--crm-origin", default="http://127.0.0.1:8001")
    parser.add_argument("--product-origin", default="http://127.0.0.1:8002")
    parser.add_argument("--site-origin", default="http://127.0.0.1:8004")
    parser.add_argument("--events-origin", default="http://127.0.0.1:8007")
    args = parser.parse_args()
    config = ScenarioConfig(args.seed, args.scenario, args.customers, args.products, args.sites, args.journeys)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dataset = ScenarioGenerator(config).dataset()
    args.output.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    result = {"output": str(args.output), "scenario": args.scenario, "seed": args.seed, "customers": args.customers, "products": args.products, "sites": args.sites, "journeys": args.journeys}
    if args.ingest:
        result["ingested"] = ScenarioIngestor({"crm": args.crm_origin, "product": args.product_origin, "site": args.site_origin, "events": args.events_origin}).ingest(dataset)
    print(json.dumps(result))


if __name__ == "__main__":
    main()