"""Product event publishing through the local event service."""

import json
import os
import time
from datetime import datetime
from urllib.error import URLError
from urllib.request import Request, urlopen


def publish_event(event_type: str, aggregate_type: str, aggregate_id: str, payload: dict, *, occurred_at: datetime) -> None:
    event_service_url = os.getenv("EVENT_SERVICE_URL")
    if not event_service_url:
        return
    envelope = {
        "source_service": "product",
        "event_type": event_type,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "payload": payload,
        "occurred_at": occurred_at.isoformat(),
        "idempotency_key": f"product:{event_type}:{aggregate_type}:{aggregate_id}:{occurred_at.isoformat()}",
        "schema_version": 1,
    }
    request = Request(f"{event_service_url.rstrip('/')}/api/events", data=json.dumps(envelope).encode(), headers={"Content-Type": "application/json"}, method="POST")
    for attempt in range(3):
        try:
            with urlopen(request, timeout=5):
                return
        except URLError:
            if attempt == 2:
                raise
            time.sleep(0.05 * (attempt + 1))