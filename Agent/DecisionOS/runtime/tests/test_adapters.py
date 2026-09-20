import json
from urllib.error import HTTPError

import pytest

from decision_os.adapters import (
    EntityAdapter,
    EventAdapter,
    ServiceAdapterError,
    ServiceAdapters,
    ServiceClient,
)
from decision_os.tools import ToolExecution


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._payload


def test_entity_adapter_uses_api_path_and_returns_normalized_provenance():
    calls = []

    def opener(request, timeout):
        calls.append((request.full_url, timeout))
        return FakeResponse({"customer_id": "c-1", "status": "active"})

    adapter = EntityAdapter(
        ServiceClient("crm", "http://crm.test", opener=opener),
        "customer",
        "customers",
    )
    result = adapter.get("c-1")

    assert calls == [("http://crm.test/api/customers/c-1", 5.0)]
    assert result.data["entity_type"] == "customer"
    assert result.data["attributes"]["status"] == "active"
    assert result.source == ("crm/api/customers/c-1",)
    assert result.evidence_references == ("crm:customer:c-1",)


def test_event_adapter_preserves_remote_filters():
    captured_url = []

    def opener(request, timeout):
        captured_url.append(request.full_url)
        return FakeResponse([])

    adapter = EventAdapter(ServiceClient("events", "http://events.test", opener=opener))
    result = adapter.list(event_type="CartCreated", correlation_id="corr-1", limit=20)

    assert "event_type=CartCreated" in captured_url[0]
    assert "correlation_id=corr-1" in captured_url[0]
    assert "limit=20" in captured_url[0]
    assert result.filters == {
        "event_type": "CartCreated",
        "correlation_id": "corr-1",
        "limit": 20,
    }


def test_adapters_reject_path_injection_and_bound_event_limit():
    adapter = EntityAdapter(ServiceClient("crm", "http://crm.test"), "customer", "customers")
    with pytest.raises(ValueError, match="Invalid customer ID"):
        adapter.get("../secret")

    events = EventAdapter(ServiceClient("events", "http://events.test"))
    with pytest.raises(ValueError, match="between 1 and 1000"):
        events.list(limit=1001)


def test_service_errors_are_normalized_without_exposing_response_body():
    def opener(request, timeout):
        raise HTTPError(request.full_url, 503, "offline", {}, None)

    client = ServiceClient("crm", "http://crm.test", opener=opener)
    with pytest.raises(ServiceAdapterError, match="crm service unavailable: HTTP 503") as error:
        client.get("/api/customers/c-1")
    assert error.value.status_code == 503


def test_service_adapters_require_all_service_origins():
    with pytest.raises(ValueError, match="Missing service origins"):
        ServiceAdapters.from_origins({"crm": "http://crm.test"})


def test_customer_snapshot_combines_only_service_adapter_results():
    class FakeAdapter:
        def __init__(self, entity_type):
            self.entity_type = entity_type

        def get(self, entity_id):
            return ToolExecution(
                data={"entity_type": self.entity_type, "entity_id": entity_id},
                source=(f"{self.entity_type}/get",),
            )

        def list(self, filters):
            return ToolExecution(
                data=[{"entity_type": self.entity_type, "filters": filters}],
                source=(f"{self.entity_type}/list",),
            )

    adapters = ServiceAdapters(
        crm=FakeAdapter("customer"),
        product=FakeAdapter("product"),
        shopping_order=FakeAdapter("order"),
        site_visit=FakeAdapter("visit"),
        marketing_campaign=FakeAdapter("campaign"),
        feedback=FakeAdapter("feedback"),
        events=FakeAdapter("event"),
        orchestration=None,
    )
    result = adapters.customer_snapshot("c-1")

    assert set(result.data) == {"customer", "orders", "visits", "feedback"}
    assert result.filters == {"customer_id": "c-1"}
    assert result.evidence_references == ("customer-snapshot:c-1",)
