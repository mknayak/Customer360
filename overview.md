# Customer360 Functional Overview

Customer360 is a synthetic enterprise application for generating customer and business activity, turning service events into governed analytics, and answering executive questions with evidence. This document describes what a user can do in the current implementation. For setup and launch instructions, see [README.md](README.md); for component boundaries and data flows, see [architecture.md](architecture.md).

## Entry Points

Start the local stack using the instructions in [README.md](README.md). The main user-facing surfaces are:

- **Simulator:** `http://127.0.0.1:8080` for customer journeys, browsing activity, and content visits.
- **Content site:** `http://127.0.0.1:8080/content.html` for synthetic content-site sessions and engagement events.
- **Executive interface:** `http://127.0.0.1:8009` for business questions and evidence-bearing briefs.
- **Agent API reference:** `http://127.0.0.1:8009/docs`.
- **Data Platform API reference:** `http://127.0.0.1:8010/docs`.

The API services are also reachable directly on their configured ports. The simulator proxies browser service requests on the same origin; it does not own or replace the operational records.

## Functional Areas

### Customer and business activity

The operational services provide APIs for the main business domains:

- CRM manages customer profiles and segments.
- Product manages products, categories, prices, and promotions.
- Shopping manages carts, orders, and payment activity.
- Site records sites, visits, and session activity.
- Feedback stores customer feedback and ratings.
- Marketing manages campaigns, audiences, channels, and interactions.
- Orchestration coordinates cross-service workflows, including shopping journeys.

The Simulator lets a user generate realistic activity through browser flows. Supported journeys include anonymous browsing, login-linked browsing, cart abandonment, successful checkout, and failed payment. Commerce actions use the operational APIs when the required customer, site, product, and service data is available.

The **User visits** workflow generates configurable content sessions, including page visits, dwell time, searches, content views, and exits. The separate content site records page and content engagement events. Session and correlation identifiers connect related activity.

For repeatable bulk data, `Enterprise/Simulator/scenario_engine.py` generates deterministic datasets when given a fixed seed. Behavior modes include `normal`, `promotion_uplift`, `website_degradation`, `product_surge`, and `feedback_spike`. Scenario ingestion can populate services and publish event batches for subsequent analytics.

### Events and operational coordination

Operational changes publish versioned event envelopes to the Events service. The envelopes preserve event identity, source, type, payload, occurrence time, and correlation metadata. Events are stored locally and can be polled, replayed, and ingested by the Data Platform; this is an HTTP event service, not a distributed streaming broker.

Orchestration coordinates multi-service work through service APIs. Individual services retain ownership of their records and local SQLite databases; other components should use their APIs or analytical projections rather than reading those database files directly.

### Analytics and data exploration

The Data Platform ingests event batches or pulls events from the Events service, then builds raw-event and curated analytical data in its own SQLite warehouse. It can also refresh selected dimensions through operational service APIs.

Users and applications can:

- Query governed KPIs, including revenue, visits, conversion, product performance, payment failures, and feedback measures.
- Request time-series trends at supported day, week, or month granularities.
- Explore payment failures grouped by approved customer profile dimensions; small groups are suppressed and customer names or IDs are not returned.
- Look up available metrics, dimensions, and filters, then execute semantic queries compiled from the approved catalog.
- Obtain scoped schema context and run a constrained, read-only SQL query. Execution accepts a single `SELECT` or `WITH` statement and applies authorization and runtime/result limits.
- Inspect catalog, data coverage, quality, and reconciliation information.

Common endpoints include `/api/kpis/{metric}`, `/api/trends`, `/api/semantic-query/context`, `/api/semantic-query/execute`, `/api/sql/context`, `/api/sql/execute`, `/api/quality`, `/api/coverage`, and `/api/catalog` on port `8010`.

### Executive decision support

The Executive interface accepts a business question and returns an evidence-oriented brief. The primary API is `POST /api/executive/brief` on the Agent application.

The current workflow checks the caller's configured permission, selects an approved metric or query path, dispatches a governed analytics tool, and formats the result. A brief can include an answer, supporting facts, source and query information, freshness, limitations, and follow-up questions. The Data Platform performs analytical calculations; the Agent does not query operational databases directly.

A configured OpenAI-compatible model can assist with selected metric/query and response-synthesis paths. Without model configuration, supported questions use deterministic local behavior. Model availability does not change the Data Platform's authorization or query validation boundaries.

The Agent application also exposes investigation creation and execution, semantic lookup, health and adapter checks, and conversation retrieval endpoints. The investigation/tool runtime is intended to make execution and evidence explicit; the current local persistence for investigations and conversations is in memory.

### Graph and document retrieval

The Agent API exposes graph sync/search/neighbors/paths and document ingestion, search, answer, and lookup routes. These are local runtime capabilities, not a claim that the graph or document corpus is automatically populated from current operational or analytical data. The graph and document stores are in-process; useful results depend on explicitly supplied data and do not persist as production stores across restarts.

## Typical Workflows

### Generate activity and ask a question

1. Use the Simulator to run customer, commerce, or content journeys, or generate a reproducible scenario dataset.
2. The operational services update their own records and publish events to the Events service.
3. Trigger or wait for Data Platform ingestion. Agent analytics requests can trigger an event-service pull and warehouse refresh.
4. Ask a business question in the Executive interface or call `POST /api/executive/brief`.
5. Review the answer together with its metric/source details, freshness, and limitations.

### Explore metrics directly

1. Call `/api/catalog` or `/api/semantic-query/context` to inspect available definitions and queryable fields.
2. Run a governed KPI request, trend request, or semantic query.
3. Use `/api/quality` and `/api/coverage` to understand the state and completeness of the available data.
4. Use the SQL context and execution routes only when a catalog metric does not express the question; SQL remains read-only and constrained.

### Reproduce a business scenario

Run the scenario engine with a fixed random seed to generate the same synthetic customer journeys again. Choose a scenario mode to create activity such as a promotion uplift, site degradation, product surge, or feedback spike, then ingest the resulting data before comparing analytics. See [Enterprise/Simulator/README.md](Enterprise/Simulator/README.md) for scenario generation and content-site details.

## Data, Governance, and Current Boundaries

- Most activity and records are synthetic. Results are not production customer facts.
- Operational services are authoritative for their own records; warehouse results are derived projections and may lag until ingestion runs.
- Approved metric definitions and Data Platform query controls govern analytics. Missing data, authorization limits, freshness, and other constraints should be treated as part of the result.
- The Agent is a decision-support interface, not a system of record. Its available write tools do not create or modify operational business records.
- The optional model is not required for deterministic supported flows and is not the source of numerical facts.
- Agent conversations, investigations, graph data, and document data use local in-process stores in the current runtime; they are not durable across application restarts.
- Graph/RAG APIs, specialist-agent specifications, and durable decision schemas do not by themselves imply automatic data projection, full multi-agent orchestration, or production persistence.

For endpoint contracts, operational service details, setup, tests, and implementation status, use the component documentation linked from [README.md](README.md) and [architecture.md](architecture.md).
