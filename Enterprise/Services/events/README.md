# Event Service

The Event service is the local event backbone. It stores immutable event envelopes in `data/events.sqlite3` and does not own operational business entities.

## API

- `POST /api/events` with optional `idempotency_key` for duplicate-safe retries
- `GET /api/events` with `event_type`, `source_service`, `correlation_id`, `recorded_after`, and `limit` filters
- `GET /api/events/replay` with bounded source/type/time filters

Events carry source service, event type, aggregate identity, payload, schema version, occurrence time, correlation metadata, and an optional idempotency key. A broker-backed dispatcher can replace this local append-only store later without changing the envelope contract.
