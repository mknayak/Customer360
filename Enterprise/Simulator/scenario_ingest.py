"""Push a generated scenario into the local enterprise APIs."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
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


def ingest_file(path: str, origins: Mapping[str, str]) -> dict[str, int]:
    with open(path, encoding="utf-8") as source:
        return ScenarioIngestor(origins).ingest(json.load(source))