# Scenario Engine

`scenario_engine.py` generates deterministic Customer360 datasets without external dependencies.

The default configuration generates 10,000 customers, 100 products, 5 sites, and 10,000 correlated journeys. Supported behavior modes are:

- `normal`
- `promotion_uplift`
- `website_degradation`
- `product_surge`
- `feedback_spike`

Generate a scenario file with:

```text
.venv/bin/python Enterprise/Simulator/scenario_engine.py \
  --output /tmp/customer360-scenario.json \
  --scenario promotion_uplift \
  --seed 42
```

Each journey includes a stable correlation ID and ordered event envelopes. Use a fixed seed to reproduce the same dataset for evaluation.

## Content site

Open `http://127.0.0.1:8080/content.html` while the simulator and Event service
are running. The content site provides the second synthetic website required by
the enterprise blueprint and records these Event service envelopes:

- `PageVisit`
- `ContentView`
- `Search`
- `TimeOnPage`
- `Exit`

All activity for a browser session shares a session and correlation ID. Content
pages and documents use stable content IDs so the events can be joined to RAG
ingestion and analytical models later.

The main simulator also includes a **User visits** view. It can generate
anonymous or customer-linked sessions across selected content pages with
configurable session count, pages per session, dwell time, search probability,
and content-view probability. Each generated session emits a correlated
`PageVisit`, optional `ContentView` and `Search` events, one `TimeOnPage` event
per page, and an `Exit` event.

Available flows are anonymous browse and exit, anonymous-to-login browsing,
cart abandonment, successful checkout, and failed payment. `Random mix` selects
one of these flows per session. Commerce flows use the real Shopping service
after login when customer, site, catalog, and service data are available.
