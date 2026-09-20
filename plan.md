# Customer360 Implementation Plan

Last updated: 2026-09-20

This is the living implementation tracker for the Customer360 synthetic enterprise. The detailed target architecture remains in `enterprise-intelligence-brain-development.md`.

## Current Status

The operational service foundation and the first governed agentic layer are implemented. The repository now has six domain services, a local Event service, an Orchestration service, a DecisionOS runtime, an Agent app, and a simulator UI integrated with the service APIs.

Validation completed:

- Agent app and DecisionOS runtime tests pass: 39 passed, 1 deselected (`multi_hop`).
- CRM, Product, Shopping, Site, Feedback, Marketing, Events, Orchestration, and Agent app health endpoints return `200` when started with `./run.sh`.
- The Agent app executive brief endpoint returns a structured response for a valid request and rejects invalid requests with `422`.
- The simulator is served on `http://127.0.0.1:8080`.
- The simulator Sites and Events tabs are present.
- A live shopping workflow creates a Site visit, Shopping cart, cart item, and correlated `VisitStarted` and `CartCreated` events.
- Invalid workflow references fail explicitly; the orchestrator does not bypass service validation.

## Completed

### Phase 0: Repository and service foundation

- [x] Shared repository `.venv` and launcher script
- [x] FastAPI service conventions
- [x] Service-owned SQLite persistence boundaries
- [x] ID-based relationships across service boundaries
- [x] Focused API tests for implemented services

### Phase 1: CRM service

- [x] Customer CRUD
- [x] Customer profiles
- [x] Customer segments
- [x] Customer bulk upsert/import path
- [x] Repository and API tests

### Phase 2: Product service

- [x] Products
- [x] Categories, prices, and promotions
- [x] Stores and store-specific catalogs
- [x] Inventory
- [x] Simulator catalog import path

### Phase 3: Shopping service

- [x] Carts and cart items
- [x] Orders and order items
- [x] Payment status and failure details
- [x] Cart abandonment and order status updates
- [x] Simulator journey and orders views

### Phase 4: Sites and simulator website

- [x] Site service
- [x] Site CRUD
- [x] Visit tracking
- [x] Simulator Sites tab
- [x] Site service proxy routing through the simulator
- [x] Site and visit records linked by customer and site IDs

### Phase 5: Feedback and Marketing services

- [x] Feedback CRUD and ratings
- [x] Campaigns, audiences, and channels
- [x] Campaign audience/channel assignments
- [x] Campaign interactions
- [x] Simulator engagement and feedback controls

### Event and orchestration foundation

- [x] Local append-only Event service on port `8007`
- [x] Typed event envelope with source, type, aggregate, payload, timestamps, schema version, and correlation metadata
- [x] Event query filters by type, source, correlation ID, and limit
- [x] Orchestration service on port `8008`
- [x] Shopping journey workflow calling Site and Shopping through APIs
- [x] Correlated `VisitStarted` and `CartCreated` events
- [x] Event service and Orchestration service included in `run.sh`
- [x] Simulator Events tab with event table, filtering, and sidebar statistics
- [x] Simulator shopping journey routed through Orchestration

### Agentic intelligence foundation

- [x] DecisionOS runtime contracts and investigation lifecycle
- [x] Governed tool catalog, permission-first dispatch, and evidence envelopes
- [x] Service adapters for operational APIs and event timelines
- [x] Bounded domain agent pack and executive orchestrator
- [x] Semantic metric governance, graph investigation, and dependency-free RAG/GraphRAG slices
- [x] Evidence validation, contradiction handling, confidence scoring, and decision records
- [x] Workflow execution with retries, timeouts, compensation hooks, and idempotency
- [x] Agent app executive brief API on port `8009`
- [x] Agent app and DecisionOS runtime test coverage

## In Progress / Next

### Productionize the agentic foundation

- [ ] Replace dependency-free graph and RAG slices with production stores and retrieval providers
- [ ] Connect analytics and semantic adapters to production data-platform implementations
- [ ] Add end-to-end evaluation fixtures for the target executive questions
- [ ] Complete durable persistence and audit storage beyond the current runtime boundary
- [ ] Add authentication, authorization, and deployment configuration for the Agent app

### Complete event capture across services

- [x] Add service-owned event publishing for CRM customer create, update, and delete changes
- [x] Add Product events for product, price, promotion, catalog, and inventory changes
- [x] Add Shopping events for cart, order, payment, abandonment, and cancellation changes
- [x] Add Site events for site and visit lifecycle changes
- [x] Add Feedback events for submissions and updates
- [x] Add Marketing events for campaign lifecycle and interactions
- [ ] Define event name, payload, schema-version, causation, and correlation conventions
- [x] Add idempotency and retry behavior for event append and service publishers
- [x] Add bounded event replay API

### Strengthen orchestration

- [x] Add durable workflow state and workflow status queries
- [ ] Add retries, timeouts, and compensation behavior
- [ ] Add checkout, payment, cancellation, and fulfillment workflow steps
- [ ] Add workflow failure and completion events
- [ ] Route all simulator multi-service actions through orchestration where appropriate
- [ ] Keep orchestration API-only; never access domain databases directly

### Phase 6: Simulation engine

The DecisionOS knowledge-graph Phase 6 slice is implemented separately in
`agentic_plan.md`. This operational Phase 6 remains focused on scalable,
repeatable business simulation. A deterministic scenario engine now supports
the required scale floors and behavior modes; API ingestion and UI controls
remain follow-up integration work.

- [x] Configurable scenario definitions
- [x] Generate 10,000+ customers
- [x] Generate 100+ products and 5-10 sites
- [x] Generate large behavioral event volumes
- [x] Simulate normal behavior, promotion uplift, website degradation, product surges, and feedback patterns
- [x] Add deterministic scenario seeds for repeatable evaluation

### Phase 7: Data platform

- [x] Event ingestion pipeline
- [x] Raw event storage
- [x] Curated analytical models
- [x] KPI query layer
- [x] Revenue, visits, conversion, cart abandonment, and product performance metrics

### Phase 8: Semantic layer

- [ ] Governed definitions for revenue, customer, retention, conversion, promotion, product performance, visit, and cart abandonment
- [ ] Metric ownership, source, grain, formula, exclusions, and effective dates
- [ ] Resolve business terms before analytical querying

### Phase 9: Knowledge graph

- [ ] Customer, Product, Promotion, Site, Segment, Campaign, Order, and Feedback entities
- [ ] Relationship synchronization from source IDs
- [ ] Multi-hop relationship queries

### Phase 10: RAG and GraphRAG

- [ ] Document ingestion and chunking
- [ ] Embeddings and vector retrieval
- [ ] Graph traversal and hybrid retrieval
- [ ] Evidence references for retrieved context

### Phase 11: Agentic intelligence

- [ ] Governed agent tools over service and analytical interfaces
- [ ] Executive Orchestrator
- [ ] Customer, Product, Promotion, Digital, Feedback, and Analytics agents
- [ ] Permission checks before retrieval and tool execution
- [ ] Evidence-backed investigation and decision contracts

### Phase 12: Executive experience

- [ ] CEO/CFO decision experience
- [ ] Conversation history
- [ ] Source and evidence view
- [ ] Charts and drill-down
- [ ] Follow-up questions

## Architectural Guardrails

- Domain services own their operational records and databases.
- Events are immutable facts, not a replacement for operational records.
- Orchestration coordinates APIs and workflows; it does not own domain data.
- Cross-service relationships use IDs.
- Analytical joins belong in the data platform.
- Agents must use governed tools and must not access operational databases directly.
- Separate facts, interpretations, hypotheses, and recommendations.
- Surface missing permissions, stale data, ambiguous metrics, and contradictory sources.
