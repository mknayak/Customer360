from Enterprise.Simulator.scenario_ingest import ScenarioIngestor


class RecordingIngestor(ScenarioIngestor):
    def __init__(self):
        super().__init__({"crm": "crm", "product": "product", "site": "site", "events": "events"})
        self.calls = []

    def _post(self, service, path, payload):
        self.calls.append((service, path, payload))
        return {}


def test_scenario_ingestor_provisions_entities_and_batches_events():
    ingestor = RecordingIngestor()
    result = ingestor.ingest({"customers": [{"customer_id": "c1"}], "products": [{"product_id": "p1"}], "sites": [{"site_id": "s1"}], "journeys": [{"events": [{"event_id": "e1"}, {"event_id": "e2"}]}]})
    assert result == {"customers": 1, "products": 1, "sites": 1, "journeys": 1, "events": 2}
    assert [call[:2] for call in ingestor.calls] == [("crm", "/api/customers/bulk"), ("product", "/api/products"), ("site", "/api/sites"), ("events", "/api/events/batch")]