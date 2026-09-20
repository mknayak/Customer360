"""Read-only HTTP adapters for governed access to enterprise services."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .tools import ToolExecution

HttpOpener = Callable[..., Any]
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class ServiceAdapterError(RuntimeError):
    """Safe, transport-level error exposed by an adapter."""

    def __init__(self, service: str, message: str, status_code: int | None = None) -> None:
        super().__init__(f"{service} service unavailable: {message}")
        self.service = service
        self.status_code = status_code


class ServiceClient:
    def __init__(
        self,
        service: str,
        origin: str,
        timeout: float = 5.0,
        opener: HttpOpener = urlopen,
    ) -> None:
        self.service = service
        self.origin = origin.rstrip("/")
        self.timeout = timeout
        self._opener = opener

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        if not path.startswith("/api/"):
            raise ValueError("Service paths must remain under /api")
        query = urlencode({key: value for key, value in (params or {}).items() if value is not None})
        url = f"{self.origin}{path}{f'?{query}' if query else ''}"
        request = Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with self._opener(request, timeout=self.timeout) as response:
                payload = response.read()
        except HTTPError as error:
            raise ServiceAdapterError(self.service, f"HTTP {error.code}", error.code) from error
        except (URLError, TimeoutError, OSError) as error:
            raise ServiceAdapterError(self.service, "request failed") from error
        try:
            return json.loads(payload)
        except (TypeError, json.JSONDecodeError) as error:
            raise ServiceAdapterError(self.service, "invalid JSON response") from error

    def health(self) -> Mapping[str, Any]:
        result = self.get("/api/health")
        if not isinstance(result, Mapping):
            raise ServiceAdapterError(self.service, "invalid health response")
        return result


def validate_identifier(value: str, field_name: str = "identifier") -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid {field_name}")
    return value


def _retrieved_at() -> str:
    return datetime.now(timezone.utc).isoformat()


class EntityAdapter:
    def __init__(self, client: ServiceClient, entity_type: str, collection: str) -> None:
        self._client = client
        self._entity_type = entity_type
        self._collection = collection

    def get(self, entity_id: str) -> ToolExecution:
        validate_identifier(entity_id, f"{self._entity_type} ID")
        path = f"/api/{self._collection}/{entity_id}"
        data = self._client.get(path)
        return ToolExecution(
            data={"entity_type": self._entity_type, "entity_id": entity_id, "attributes": data},
            source=(f"{self._client.service}{path}",),
            query_metadata={"service": self._client.service, "path": path, "method": "GET"},
            freshness={"retrieved_at": _retrieved_at()},
            evidence_references=(f"{self._client.service}:{self._entity_type}:{entity_id}",),
        )

    def list(self, filters: Mapping[str, Any] | None = None) -> ToolExecution:
        path = f"/api/{self._collection}"
        data = self._client.get(path, filters)
        return ToolExecution(
            data=data,
            source=(f"{self._client.service}{path}",),
            filters=dict(filters or {}),
            query_metadata={"service": self._client.service, "path": path, "method": "GET"},
            freshness={"retrieved_at": _retrieved_at()},
        )


class EventAdapter:
    def __init__(self, client: ServiceClient) -> None:
        self._client = client

    def list(
        self,
        *,
        event_type: str | None = None,
        source_service: str | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> ToolExecution:
        if not 1 <= limit <= 1000:
            raise ValueError("Event limit must be between 1 and 1000")
        filters = {
            "event_type": event_type,
            "source_service": source_service,
            "correlation_id": correlation_id,
            "limit": limit,
        }
        data = self._client.get("/api/events", filters)
        return ToolExecution(
            data=data,
            source=("events/api/events",),
            filters={key: value for key, value in filters.items() if value is not None},
            query_metadata={"service": self._client.service, "path": "/api/events", "method": "GET"},
            freshness={"retrieved_at": _retrieved_at()},
        )


@dataclass(frozen=True)
class ServiceAdapters:
    crm: EntityAdapter
    product: EntityAdapter
    shopping_order: EntityAdapter
    site_visit: EntityAdapter
    marketing_campaign: EntityAdapter
    feedback: EntityAdapter
    events: EventAdapter
    orchestration: ServiceClient

    @classmethod
    def from_origins(cls, origins: Mapping[str, str], timeout: float = 5.0) -> "ServiceAdapters":
        clients = {
            name: ServiceClient(name, origin, timeout)
            for name, origin in origins.items()
        }
        required = {
            "crm",
            "product",
            "shopping",
            "site",
            "marketing",
            "feedback",
            "events",
            "orchestration",
        }
        missing = required - set(clients)
        if missing:
            raise ValueError(f"Missing service origins: {', '.join(sorted(missing))}")
        return cls(
            crm=EntityAdapter(clients["crm"], "customer", "customers"),
            product=EntityAdapter(clients["product"], "product", "products"),
            shopping_order=EntityAdapter(clients["shopping"], "order", "orders"),
            site_visit=EntityAdapter(clients["site"], "visit", "visits"),
            marketing_campaign=EntityAdapter(clients["marketing"], "campaign", "campaigns"),
            feedback=EntityAdapter(clients["feedback"], "feedback", "feedback"),
            events=EventAdapter(clients["events"]),
            orchestration=clients["orchestration"],
        )

    def entity_mapping(self, entity_type: str, entity_id: str) -> ToolExecution:
        adapters = {
            "customer": self.crm,
            "product": self.product,
            "order": self.shopping_order,
            "visit": self.site_visit,
            "campaign": self.marketing_campaign,
            "feedback": self.feedback,
        }
        try:
            return adapters[entity_type].get(entity_id)
        except KeyError as error:
            raise ValueError(f"Unsupported entity type: {entity_type}") from error

    def customer_snapshot(self, customer_id: str) -> ToolExecution:
        validate_identifier(customer_id, "customer ID")
        customer = self.crm.get(customer_id)
        orders = self.shopping_order.list({"customer_id": customer_id})
        visits = self.site_visit.list({"customer_id": customer_id})
        feedback = self.feedback.list({"customer_id": customer_id})
        return ToolExecution(
            data={
                "customer": customer.data,
                "orders": orders.data,
                "visits": visits.data,
                "feedback": feedback.data,
            },
            source=customer.source + orders.source + visits.source + feedback.source,
            filters={"customer_id": customer_id},
            query_metadata={"operation": "customer_snapshot", "services": ["crm", "shopping", "site", "feedback"]},
            freshness={"retrieved_at": _retrieved_at()},
            evidence_references=(f"customer-snapshot:{customer_id}",),
        )

    def health(self) -> dict[str, Mapping[str, Any] | dict[str, str]]:
        adapters = {
            "crm": self.crm,
            "product": self.product,
            "shopping": self.shopping_order,
            "site": self.site_visit,
            "marketing": self.marketing_campaign,
            "feedback": self.feedback,
            "events": self.events,
            "orchestration": self.orchestration,
        }
        result: dict[str, Mapping[str, Any] | dict[str, str]] = {}
        for name, adapter in adapters.items():
            try:
                client = adapter if isinstance(adapter, ServiceClient) else adapter._client
                result[name] = client.health()
            except ServiceAdapterError as error:
                result[name] = {"status": "unavailable", "detail": str(error)}
        return result
