# Customer360 Implementation Plan

Last updated: 2026-09-21

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
- [ ] Add a real LLM-backed investigation loop with bounded planning, tool calls, evidence validation, and final synthesis
- [ ] Replace deterministic intent matching and analytics fallbacks with governed live service and analytics execution
- [ ] Add row-level and field-level authorization, PII masking, consent checks, and audit inspection
- [ ] Add production observability for agent, tool, workflow, data freshness, and evidence failures

### Scope reconciliation against the development blueprint

The repository currently implements the blueprint as a local, dependency-free MVP. The following items remain required for the complete Enterprise Intelligence Brain described in `enterprise-intelligence-brain-development.md`:

- [ ] Build Website 2, the content site, with About, Products, News, Blog, Customer Stories, Sustainability, and Company Information content
- [ ] Capture content-site `PageVisit`, `ContentView`, `Search`, `TimeOnPage`, and `Exit` events
- [ ] Add a production event backbone or documented deployment alternative with durable delivery, consumer management, monitoring, and dead-letter handling
- [ ] Finalize event conventions for names, payloads, schema versions, causation IDs, correlation IDs, ordering, and compatibility
- [ ] Connect simulation scenarios to service APIs and expose scenario parameters and controls in the simulator UI
- [ ] Extend the data platform beyond SQLite MVP storage with batch/streaming ingestion, data quality checks, catalog, lineage, and scalable warehouse storage
- [ ] Add finance data sources and governed metrics for cost, margin, profit, forecast, budget variance, and promotion economics
- [ ] Expand semantic mappings across service APIs, analytical models, graph entities, calculation rules, data owners, and security classifications
- [ ] Replace in-process graph and document stores with durable graph, vector, embedding, and document retrieval providers
- [ ] Complete checkout, payment, cancellation, fulfillment, retry, timeout, compensation, and workflow failure/completion event paths
- [ ] Add durable investigation, evidence, decision, memory, and audit persistence with versioning and retention enforcement
- [ ] Add end-to-end evaluation fixtures for the six target executive questions in the blueprint

### Production completion gates

- [ ] All executive answers use live governed data; no deterministic fallback is presented as an enterprise fact
- [ ] Every answer exposes source, definition, calculation/query, time period, filters, freshness, and authorization context
- [ ] Unsupported causal claims, stale data, contradictory sources, missing permissions, and incomplete data block or qualify recommendations
- [ ] A CEO/CFO can complete the target question set end-to-end through the executive experience
- [ ] Deployment, secrets/configuration, authentication, authorization, monitoring, backup, and recovery procedures are documented and tested

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

- [x] Governed definitions for revenue, customer, retention, conversion, promotion, product performance, visit, and cart abandonment
- [x] Metric ownership, source, grain, formula, exclusions, and effective dates
- [x] Resolve business terms before analytical querying

### Phase 9: Knowledge graph

- [x] Customer, Product, Promotion, Site, Segment, Campaign, Order, and Feedback entities
- [x] Relationship synchronization from source IDs
- [x] Multi-hop relationship queries

### Phase 10: RAG and GraphRAG

- [x] Document ingestion and chunking
- [x] Embeddings and vector retrieval
- [x] Graph traversal and hybrid retrieval
- [x] Evidence references for retrieved context

### Phase 11: Agentic intelligence

- [x] Governed agent tools over service and analytical interfaces
- [x] Executive Orchestrator
- [x] Customer, Product, Promotion, Digital, Feedback, and Analytics agents
- [x] Permission checks before retrieval and tool execution
- [x] Evidence-backed investigation and decision contracts

### Phase 12: Executive experience

- [x] CEO/CFO decision experience
- [x] Conversation history
- [x] Source and evidence view
- [x] Charts and drill-down
- [x] Follow-up questions

## Remaining Delivery Phases

The phases below extend the local MVP roadmap into the production-capable Enterprise Intelligence Brain described in `enterprise-intelligence-brain-development.md`. Each phase should be completed and validated before the next dependent phase begins.

### Phase 13: Content site and unstructured activity

**Goal:** Complete the second website required by the synthetic enterprise and make content behavior available to the event and RAG layers.

- [x] Build the static content site with About, Products, News, Blog, Customer Stories, Sustainability, and Company Information pages
- [x] Add content-site entry point and local launch configuration through the simulator server
- [x] Capture `PageVisit`, `ContentView`, `Search`, `TimeOnPage`, and `Exit` activity
- [x] Publish typed events with site, session, page, schema-version, idempotency, and correlation metadata
- [x] Add configurable simulator user-visit sessions across selected content pages
- [ ] Ingest approved content and business documents into the document store

**Acceptance criteria:** A content journey produces queryable events, and an authorized RAG query can cite the originating page or document.

### Phase 14: Event backbone and contract governance

**Goal:** Make domain events reliable, compatible, replayable, and consumable by multiple downstream systems.

- [ ] Select and document the production messaging option and local development equivalent
- [x] Define a local event contract registry for event names, source services, payload shape, and schema version
- [ ] Finalize production ordering, compatibility, and evolution rules
- [ ] Add publisher retries, consumer retries, dead-letter handling, and idempotent consumers
- [x] Add bounded batch ingestion and replay cursor support
- [ ] Add consumer registration, offsets/checkpoints, dead-letter handling, and event delivery metrics
- [x] Add Event service contract and idempotency tests
- [ ] Add contract tests for every service-owned publisher
- [ ] Emit workflow failure and completion events

**Acceptance criteria:** A consumer can recover from delivery failure, replay a bounded time range safely, and reject incompatible event schemas without data loss.

### Phase 15: Simulation-to-enterprise integration

**Goal:** Turn deterministic scenarios into repeatable end-to-end enterprise data generation.

- [x] Add scenario ingestor for generated CRM, Product, Site, and Event service data
- [ ] Connect scenario generation to Shopping, Feedback, Marketing, and Content APIs
- [ ] Expose scenario selection, seed, scale, date range, and behavior parameters in the simulator UI
- [ ] Generate promotion uplift, website degradation, product surge, site launch, and feedback patterns through real service workflows
- [x] Record stable scenario event IDs, seeds, schema versions, idempotency keys, correlation IDs, and causation IDs
- [ ] Add reset, replay, and verification commands for generated datasets

**Acceptance criteria:** The same scenario seed produces reproducible service records, events, KPIs, and investigation results.

### Phase 16: Production analytical platform and finance model

**Goal:** Expand the SQLite analytical MVP into a governed platform that supports enterprise executive metrics.

- [x] Extend raw and curated SQLite layers with content activity and finance facts
- [x] Add basic data quality metadata for raw event count, latest event time, and curated row counts
- [ ] Add batch and streaming ingestion paths with raw, cleansed, curated, and analytical layers
- [ ] Add complete data quality checks for completeness, uniqueness, freshness, referential integrity, and reconciliation
- [ ] Add catalog and lineage metadata for every curated metric
- [ ] Add time-period, site, region, channel, segment, product, promotion, and new-versus-existing customer dimensions
- [x] Add finance model fields and KPIs for revenue, cost, margin, profit, and promotion-linked orders
- [ ] Add finance sources for forecast, budget variance, and complete promotion economics
- [ ] Reconcile analytical totals against operational service totals

**Acceptance criteria:** Revenue, conversion, retention, abandonment, product performance, and promotion economics are reproducible from governed analytical models with freshness and quality status.

### Phase 17: Enterprise semantic and knowledge layer

**Goal:** Make business concepts, relationships, definitions, and lineage durable and consistently resolvable.

- [ ] Move metric definitions from the in-process registry to a versioned durable semantic catalog
- [ ] Map business terms to service APIs, analytical models, graph entities, formulas, owners, effective dates, and security classifications
- [ ] Add ambiguity, deprecation, and definition-conflict workflows
- [ ] Replace the in-process graph with a durable graph store and repeatable synchronization jobs
- [ ] Add graph refresh checkpoints, source lineage, entity resolution, and relationship quality checks
- [ ] Replace dependency-free document/vector retrieval with production stores and embedding providers

**Acceptance criteria:** An investigation resolves the same business term consistently across API, analytics, graph, and document retrieval, with versioned lineage.

### Phase 18: Durable DecisionOS persistence and governance

**Goal:** Make investigations, decisions, evidence, memory, and audits durable, reviewable, and policy-controlled.

- [ ] Implement durable persistence for investigations, workflow state, evidence packages, decisions, memory, and audit events
- [ ] Add immutable evidence references and versioned decision records
- [ ] Enforce retention, deletion, legal hold, correction, and consent policies
- [ ] Add row-level and field-level authorization, PII masking, aggregation thresholds, and sensitivity labels
- [ ] Add authentication, RBAC, service identity, secret management, and authorization audit inspection
- [ ] Ensure every tool fails closed when authorization or policy evaluation is unavailable

**Acceptance criteria:** Unauthorized data is never retrieved, sensitive fields are masked according to policy, and an auditor can reconstruct who accessed which evidence and why.

### Phase 19: Real agent runtime and investigation execution

**Goal:** Replace deterministic demonstration behavior with a governed, model-backed investigation loop.

- [ ] Add an LLM provider abstraction with timeout, quota, retry, and failure handling
- [ ] Implement question intake, scope clarification, entity and metric identification, investigation planning, and bounded tool execution
- [ ] Route work to domain agents using explicit role, tool, memory, and escalation contracts
- [ ] Require semantic lookup before quantitative queries and permission checks before retrieval
- [ ] Validate claims, contradictions, confidence, causality limits, and recommendation eligibility before synthesis
- [ ] Remove enterprise-facing deterministic fallbacks or label them explicitly as test-only data

**Acceptance criteria:** A target executive question completes through live governed tools and returns a decision brief whose claims all reference validated evidence.

### Phase 20: Complete business workflows and executive investigations

**Goal:** Cover the cross-service journeys and executive analyses required by the blueprint.

- [ ] Add checkout, payment, cancellation, fulfillment, and compensation workflow steps
- [ ] Add workflow idempotency keys, retries, timeouts, recovery, and operator status controls
- [ ] Add before/during/after promotion analysis with incrementality limitations
- [ ] Add mobile funnel, site, channel, region, segment, product, and cohort breakdowns
- [ ] Add complaint, sentiment, topic, intent, product, and site relationships for Voice of Customer analysis
- [ ] Add finance cross-checks for revenue, margin, cost, and forecast implications

**Acceptance criteria:** The six target executive questions in the blueprint complete end-to-end with facts, drivers, limitations, evidence, and recommended next actions.

### Phase 21: Production deployment, observability, and evaluation

**Goal:** Operate and verify the system as a production-style platform.

- [ ] Add deployment configuration, environment-specific settings, migrations, backups, and recovery procedures
- [ ] Add service health, dependency health, event lag, data freshness, tool latency, model usage, and failure dashboards
- [ ] Add distributed request, correlation, and audit tracing without exposing secrets or hidden reasoning
- [ ] Add regression fixtures for permissions, stale data, missing data, contradictory evidence, and unsupported causality
- [ ] Add quality, latency, cost, and groundedness evaluation for every target executive question
- [ ] Document operational runbooks, incident response, rollback, and data repair procedures

**Acceptance criteria:** The platform can be deployed from documented configuration, monitored during a representative workload, recovered from a tested failure, and pass the end-to-end evaluation suite.

## Architectural Guardrails

- Domain services own their operational records and databases.
- Events are immutable facts, not a replacement for operational records.
- Orchestration coordinates APIs and workflows; it does not own domain data.
- Cross-service relationships use IDs.
- Analytical joins belong in the data platform.
- Agents must use governed tools and must not access operational databases directly.
- Separate facts, interpretations, hypotheses, and recommendations.
- Surface missing permissions, stale data, ambiguous metrics, and contradictory sources.
