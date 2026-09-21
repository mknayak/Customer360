"""Push a generated scenario into the local enterprise APIs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.request import Request, urlopen


class ScenarioIngestor:
    def __init__(self, origins: Mapping[str, str]) -> None:
        self.origins = dict(origins)

    def _post(self, service: str, path: str, payload: object) -> object:
        request = Request(
            f"{self.origins[service].rstrip('/')}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read())

    def _get(self, service: str, path: str) -> object:
        with urlopen(f"{self.origins[service].rstrip('/')}{path}", timeout=15) as response:
            return json.loads(response.read())

    def ingest(self, dataset: Mapping[str, object], *, event_batch_size: int = 500) -> dict[str, int]:
        customers = list(dataset.get("customers", []))
        products = list(dataset.get("products", []))
        sites = list(dataset.get("sites", []))
        journeys = list(dataset.get("journeys", []))
        if customers:
            self._post("crm", "/api/customers/bulk", customers)
        for product in products:
            self._post("product", "/api/products", product)
        for site in sites:
            self._post("site", "/api/sites", site)
        events = [event for journey in journeys for event in journey.get("events", [])]
        for start in range(0, len(events), event_batch_size):
            self._post("events", "/api/events/batch", {"events": events[start:start + event_batch_size]})
        return {"customers": len(customers), "products": len(products), "sites": len(sites), "journeys": len(journeys), "events": len(events)}

    def replay(self, dataset: Mapping[str, object], *, event_batch_size: int = 500) -> dict[str, int]:
        """Replay only deterministic event envelopes; idempotency makes this safe."""
        events = [event for journey in dataset.get("journeys", []) for event in journey.get("events", [])]
        sent = 0
        for start in range(0, len(events), event_batch_size):
            self._post("events", "/api/events/batch", {"events": events[start:start + event_batch_size]})
            sent += len(events[start:start + event_batch_size])
        return {"events": sent}

    def verify(self, dataset: Mapping[str, object]) -> dict[str, Any]:
        expected = {"customers": len(list(dataset.get("customers", []))), "products": len(list(dataset.get("products", []))), "sites": len(list(dataset.get("sites", [])))}
        actual = {"customers": self._get("crm", "/api/customers?page=1&page_size=1").get("total", 0), "products": len(self._get("product", "/api/products")), "sites": len(self._get("site", "/api/sites"))}
        return {"expected": expected, "actual": actual, "matched": {key: expected[key] <= actual[key] for key in expected}}


def ingest_file(path: str, origins: Mapping[str, str]) -> dict[str, int]:
    with open(path, encoding="utf-8") as source:
        return ScenarioIngestor(origins).ingest(json.load(source))