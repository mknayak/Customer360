# Customer360 Data Platform

The data platform consumes immutable Event service envelopes, preserves them in
`raw_events`, and builds small curated SQLite models for analytical queries.

Run its API from the repository root (it is also included in `run.sh` on port `8010`):

```text
PYTHONPATH=Enterprise/DataPlatform .venv/bin/python -m uvicorn data_platform.app:app --app-dir Enterprise/DataPlatform --port 8010
```

Endpoints:

- `POST /api/ingest/events` for event batches
- `POST /api/ingest/event-service` to pull from the Event service
- `GET /api/kpis/revenue`
- `GET /api/kpis/visits`
- `GET /api/kpis/conversion`
- `GET /api/kpis/cart_abandonment`
- `GET /api/kpis/product_performance`

Raw ingestion is idempotent by `event_id`, `idempotency_key`, or a canonical
event hash. Curated tables are derived only from ingested event envelopes.