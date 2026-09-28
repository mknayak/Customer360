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
- `POST /api/semantic-query/context` to retrieve a compact, relevant semantic query surface
- `POST /api/semantic-query/execute` to validate query IR, compile parameterized SQL, and execute it
- `POST /api/payment-failures/by-profile` with `principal_id` and `dimension` (`country` or `age_group`) to group PaymentFailed event counts by current CRM customer attributes

Payment-failure profile breakdowns resolve event order IDs through curated orders,
read CRM profiles only after commerce authorization, and return aggregate counts
without names or customer IDs. Groups with fewer than three distinct customers
are suppressed; missing profiles are reported as unmatched events. These are
failure counts, not failure rates (payment-attempt denominators are not available),
and current profile attributes must not be interpreted as historical demographics.

Raw ingestion is idempotent by `event_id`, `idempotency_key`, or a canonical
event hash. Curated tables are derived only from ingested event envelopes.

## SemanticQueryPlanner

The planner does not expose the complete warehouse schema to an LLM and does
not accept SQL from callers. It provides two governed operations:

1. Retrieve relevant metric, model, dimension, filter, lineage, owner, and
	classification metadata for a business question.
2. Accept a constrained query IR containing a catalog metric, approved
	dimensions and filters, sort direction, and row limit.

The Data Platform validates authorization, field compatibility, and named join
paths, compiles parameterized read-only SQL from allowlisted catalog
expressions, executes it, and returns rows with definition, source model,
lineage, and classification. A query may request names such as `orders`, but
the catalog owns the table, aliases, join keys, join type, and join order.
Callers never provide SQL or `ON` clauses.

Example query IR:

```json
{
  "principal_id": "cfo-1",
  "metric": "product_performance",
  "dimensions": ["customer", "product"],
  "joins": ["orders"],
  "metric": "page_dropoff",
  "dimensions": ["page"],
  "filters": {},
  "order": "desc",
  "limit": 10
}
```