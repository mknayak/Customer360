# Orchestration Service

The Orchestration service coordinates multi-service workflows through HTTP APIs. It does not access service databases directly and does not own customer, site, or shopping records.

## API

- `POST /api/workflows/shopping-journey`
- `GET /api/health`

The initial workflow starts a Site visit, creates a Shopping cart and cart items, and publishes `VisitStarted` and `CartCreated` events with a shared correlation ID. Later workflows can add checkout, payment, compensation, retries, and durable workflow state.
