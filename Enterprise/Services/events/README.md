# Event Service

The Event service is the local event backbone. It stores immutable event envelopes in `data/events.sqlite3` and does not own operational business entities.

## API

- `POST /api/events`
- `GET /api/events` with `event_type`, `source_service`, `correlation_id`, and `limit` filters

Events carry source service, event type, aggregate identity, payload, schema version, occurrence time, and correlation metadata. A broker-backed dispatcher can replace this local append-only store later without changing the envelope contract.
