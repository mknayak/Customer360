# Agentic Layer Implementation Plan

## Objective

Build the next layer of the Customer360 platform: a governed, evidence-first agentic intelligence system that sits on top of the operational service layer already in place. The primary goal is to convert business questions into bounded investigations, retrieve trusted facts from APIs, analytics, semantic definitions, and knowledge graph context, and return concise, evidence-backed executive decisions without bypassing governance.

This plan extends the existing operational foundations in the repo and follows the architecture already described in `enterprise-intelligence-brain-development.md` and the DecisionOS design in `Agent/DecisionOS/README.md`.

---

## 1. Design Principles

1. The LLM is an investigator, not the system of record.
2. Operational services remain the source of truth for transactional records.
3. Analytics is the source of truth for numerical facts and KPIs.
4. The knowledge graph is the source of truth for entities and relationships.
5. RAG is used for unstructured context, policies, briefs, and reports.
6. Every answer must preserve provenance: source, metric definition, time period, filters, and freshness.
7. Authorization is checked before any retrieval or tool execution.
8. The system must separate facts, interpretations, hypotheses, and recommendations.
9. Claims must be evidence-backed and auditable.
10. Missing data, stale data, and contradictory evidence must be surfaced explicitly instead of quietly resolved.

---

## 2. Target Architecture

```text
User / Executive UI
        |
        v
Executive Orchestrator
        |
        +--> Domain Agents
        |       - Customer Intelligence
        |       - Product Intelligence
        |       - Promotion Intelligence
        |       - Digital Intelligence
        |       - Voice of Customer
        |       - Finance Intelligence
        |
        +--> Governed Tools
        |       - analytics-query
        |       - semantic-lookup
        |       - graph-search
        |       - rag-search
        |       - permission-check
        |       - scenario-run
        |       - lineage-explain
        |       - decision-evaluate
        |
        +--> Memory + Persistence
        |       - working memory
        |       - conversation memory
        |       - decision memory
        |       - audit logs
        |
        +--> Evidence Validator
                - claim validation
                - confidence scoring
                - recommendation gate
```

---

## 3. Functional Scope

The agentic layer must support the following executive and domain investigation patterns:

- Customer retention and segment performance
- Product demand and category trends
- Promotion uplift and incrementality
- Website conversion, cart abandonment, and session quality
- Customer sentiment and complaint-driven issues
- Revenue, margin, and site performance analysis
- Cross-domain root-cause investigation
- Decision-quality summaries with evidence and recommendation blocks

Example question types:

- “Why did conversion fall last week?”
- “Which customer segment responded best to the new campaign?”
- “Did the promotion increase basket size or just traffic?”
- “What is driving cart abandonment for mobile visitors?”
- “Which products underperform relative to forecast?”

---

## 4. Delivery Phases

## Phase 1: Agent runtime foundation

**Status: Complete**

### Goal
Establish the minimal executable DecisionOS runtime and make it ready for service-backed investigations.

### Deliverables
- [x] Finalize DecisionOS runtime package under `Agent/DecisionOS/runtime/`
- [x] Standardized investigation state machine
- [x] Typed contracts for:
  - investigation
  - evidence
  - permission decision
  - tool request
  - decision brief
- [x] Replaceable persistence interface
- [x] Deterministic evaluator for claim validation
- [x] Tool registry and permission-first dispatcher

### Work items
- [x] Confirm the in-memory runtime is the base contract and not the final production implementation.
- [x] Add a persistence adapter boundary for SQLite/Postgres-ready storage.
- [x] Add explicit state transitions:
  - created
  - planned
  - running
  - validating
  - completed
  - failed
- [x] Add claim evaluation primitives for matched claims, missing claims, contradictions, and confidence scoring.

### Acceptance criteria
- [x] A new investigation can be created and progressed through lifecycle states.
- [x] Tool dispatch denies unauthorized access before a tool handler runs.
- [x] Decision evaluation can validate expected claims and identify missing evidence.

---

## Phase 2: Tool contracts and governed adapters

**Status: Complete**

### Goal
Define a strict set of tools that agents are allowed to call and ensure those tools enforce permission and provenance.

### Tool categories

#### 2.1 Analytics tools
- `analytics.query`
- `analytics.segment`
- `analytics.funnel`
- `analytics.compare_periods`

#### 2.2 Semantic tools
- `semantic.lookup`
- `semantic.metric_definition`
- `semantic.entity_mapping`

#### 2.3 Graph tools
- `graph.search`
- `graph.neighbors`
- `graph.paths`
- `graph.relationship_summary`

#### 2.4 RAG tools
- `rag.search`
- `rag.document_lookup`
- `rag.policy_retrieve`

#### 2.5 Permission and governance tools
- `permission.check`
- `decision.evaluate`
- `lineage.explain`

### Tool contract requirements
Each tool must define:
- name
- description
- resource
- input schema
- expected output schema
- auth requirement
- provenance metadata
- timeout and retry policy
- error model

### Work items
- [x] Build tool catalog under `Agent/DecisionOS/tools/`
- [x] Standardize `tool-contract.md` implementation
- [x] Register cataloged tools with the dispatcher through handler injection
- [x] Add permission mapping by principal and resource
- [x] Add result envelopes with:
  - status
  - source
  - generated_at
  - query metadata
  - evidence references

### Acceptance criteria
- [x] An unauthorized tool call is blocked before execution.
- [x] Every tool output carries enough metadata to trace the source query.
- [x] Tool results can be aggregated into an evidence package.

---

## Phase 3: Service adapter layer

**Status: Complete**

### Goal
Connect agents to the existing operational services and event stream through controlled adapters rather than direct database access.

### Services to integrate
- CRM service
- Product service
- Shopping service
- Site service
- Feedback service
- Marketing service
- Event service
- Orchestration service

### Adapter responsibilities
- normalize service response schemas
- validate IDs and request integrity
- map domain objects to investigation entities
- enforce safe retrieval patterns
- add timeout and failure semantics
- add remote query filtering for large result sets

### Work items
- [x] Create a service client layer in DecisionOS runtime
- [x] Add adapters for customer, product, order, visit, campaign, feedback, and event data
- [x] Add API wrappers for cross-service queries
- [x] Add service health checks and fail-closed handling
- [x] Add event-based event sourcing retrieval patterns for timeline views

### Acceptance criteria
- [x] The agent reaches the correct service endpoint without database bypass.
- [x] Service errors are translated into investigation-safe failure messages.
- [x] Multi-hop investigations can combine multiple service views without violating boundaries.

---

## Phase 4: Domain agent pack

**Status: Complete**

### Goal
Create specialized agents that each operate under a bounded scope and produce structured outputs.

### Agent set

#### Executive Orchestrator
- Coordinates the full investigation workflow
- Delegates to domain agents based on question type
- Merges evidence and controls final brief

#### Customer Intelligence Agent
- Handles customer behavior, retention, lifetime value, segments, and experience quality
- Uses CRM + site + event + feedback data

#### Product Intelligence Agent
- Focuses on inventory, category performance, product demand, price elasticity, and product quality signals

#### Promotion Intelligence Agent
- Analyzes campaign uplift, channel performance, segment response, and offer efficiency

#### Digital Intelligence Agent
- Investigates site performance, conversion funnel, traffic quality, visits, cart abandonment, and channel quality

#### Voice of Customer Agent
- Reviews feedback, complaints, sentiment, issue themes, and dissatisfaction drivers

#### Finance Intelligence Agent
- Cross-checks revenue, margin, funnel economics, and cost/benefit implications

#### Evidence Validator
- Checks if facts are supported
- Validates assumptions, confidence, and contradictions
- Prevents unsupported causal claims

#### Memory Steward
- Manages durable and constrained memory retention policies
- Keeps retrieval scoped to authorized context

### Agent contract requirements
Each agent must have:
- role definition
- allowed tools
- memory boundary
- required inputs
- expected output schema
- escalation rules
- failure behavior

### Acceptance criteria
- [x] Each agent can answer within its bounded domain without direct access to operational databases.
- [x] The orchestrator can route questions to the correct agent.
- [x] Final decision output includes evidence references and confidence status.

---

## Phase 5: Semantic layer and metric governance

**Status: Complete**

### Goal
Define the business metrics and their meaning before analytical querying.

### Required metric catalog
- revenue
- customer retention
- conversion rate
- cart abandonment rate
- basket size
- site visit volume
- campaign uplift
- product sell-through
- promotion efficiency
- repeat purchase rate

### Required governance metadata per metric
- business definition
- source table/service
- grain
- formula
- time period semantics
- exclusions
- freshness requirements
- owner
- confidence / quality notes

### Work items
- [x] Add metric definitions in DecisionOS or domain-specific metadata layer
- [x] Define business terms and synonyms
- [x] Add metric lineage from service APIs to analytical queries
- [x] Add “ambiguous metric” handling when definitions conflict

### Acceptance criteria
- [x] The agent can retrieve the definition of a metric instead of guessing it.
- [x] The same business term resolves consistently across teams.
- [x] The system surfaces missing or stale metric definitions before proceeding with a recommendation.

---

## Phase 6: Knowledge graph and entity relationships

**Status: Complete (dependency-free runtime slice)**

### Goal
Add a graph layer that helps answer relationship-driven questions and support multi-hop reasoning.

### Core entities
- Customer
- Segment
- Product
- Category
- Promotion
- Campaign
- Site
- Visit
- Order
- Cart
- Feedback
- Region

### Relationships
- customer -> segment
- customer -> order
- customer -> visit
- customer -> feedback
- product -> category
- product -> promotion
- site -> visit
- campaign -> audience
- campaign -> interaction
- order -> cart -> item -> product

### Work items
- [x] Define graph schema and node/edge conventions
- [x] Sync entities from service IDs and references through `GraphStore.sync`
- [x] Provide a deterministic refresh port for relationship synchronization
- [x] Implement bounded graph search, neighbor, path, and relationship-summary queries
- [x] Add lineage mapping from graph entities and edges to source references

### Acceptance criteria
- It can answer questions like “which products are commonly bought by customers in segment X?”
- The graph explains relationship paths rather than simply returning flat rows.
- Relationship queries can feed the orchestrator with context before final reasoning.

---

## Phase 7: RAG and GraphRAG foundation

**Status: Complete (dependency-free runtime slice)**

### Goal
Support unstructured business context and retrieval for plans, policies, reports, and briefing documents.

### Components
- document ingestion
- chunking
- embeddings
- vector retrieval
- hybrid retrieval with graph context
- evidence references

### Use cases
- policy interpretation
- campaign brief context
- product launch notes
- support issue summaries
- executive memo retrieval

### Work items
- [x] Add document store and indexing pattern
- [x] Add retrieval API for policy and brief documents
- [x] Add hybrid retrieval combining vector + graph context
- [x] Add citation metadata for every retrieved document

### Acceptance criteria
- Retrieved documents include source references and context snippets.
- The agent can explain what document supported a recommendation.
- The system distinguishes between retrieved facts and model-generated interpretation.

---

## Phase 8: Evidence pipeline and validation

**Status: Complete (dependency-free runtime slice)**

### Goal
Ensure the system generates evidence-backed recommendations rather than unsupported narratives.

### Evidence requirements
Every final answer should include:
1. question addressed
2. direct answer
3. observed facts
4. key drivers
5. confidence and limitations
6. evidence sources and lineage
7. recommended next actions
8. follow-up questions

### Validation layers
- permission validation
- schema validation
- fact validation
- contradiction detection
- confidence scoring
- recommendation gate

### Work items
- [x] Create `decision-record` output schema
- [x] Add evidence assembly from tools and retrieved sources
- [x] Add contradiction detection when sources disagree
- [x] Make recommendation output explicit and separate from facts

### Acceptance criteria
- A decision brief cannot be generated without evidence.
- Unsupported causal explanations are rejected.
- Missing permissions, stale data, or contradictory sources are surfaced in the final answer.

---

## Phase 9: Decision orchestration and workflow execution

**Status: Complete (dependency-free runtime slice)**

### Goal
Turn multiple tool calls and domain investigations into a controlled executive decision workflow.

### Workflow stages
1. Intake and clarify scope
2. Detect domain and required evidence
3. Check permissions
4. Retrieve metric definitions
5. Query relevant data sources
6. Validate facts and relationships
7. Run scenario comparisons when needed
8. Assemble decision brief
9. Surface confidence and limitations

### Work items
- [x] Add orchestration workflow state machine with durable record IDs
- [x] Add retry and timeout rules for service calls
- [x] Add compensation hooks for failed multi-step analyses
- [x] Add workflow idempotency for repeated investigations
- [x] Add decision summaries for auditability

### Acceptance criteria
- A complex question can be completed without manual ad hoc coordination.
- Failure states are explicit and recoverable.
- The runtime records what evidence was used and what was omitted.

---

## Phase 10: Executive experience

### Goal
Wrap the agentic layer in a usable, decision-oriented experience for executives.

### Experience requirements
- question input
- answer summary
- metric cards
- evidence panel
- graph/relationship view
- drill-down from insight to underlying facts
- conversation memory and prior context
- recommended next action cards

### Work items
- Add executive UI shell or route layer
- Integrate with DecisionOS responses
- Add source and evidence views
- Add chart-ready outputs for top metrics
- Add follow-up recommendation prompts

### Acceptance criteria
- The user can ask a business question and receive a structured brief.
- The answer is clearly traceable to service, metric, and evidence sources.
- The UI can expose drill-down without exposing raw system internals.

---

## 5. Implementation Sequencing

Recommended order for execution:

1. Complete the runtime contract and tooling boundary
2. Add permissions and evidence envelopes
3. Wire agents to the service adapters
4. Implement the core domain agents
5. Add metric governance and semantic definitions
6. Add graph entity sync and relationship queries
7. Add RAG and hybrid retrieval
8. Add validation and decision summarization
9. Add the executive UX layer
10. Run end-to-end evaluations on representative business questions

---

## 6. Detailed Execution Milestones

### Milestone A: Runtime ready
- Investigation engine complete
- Tool dispatcher complete
- Permission gate complete
- Decision evaluator complete

### Milestone B: Service-connected agent runtime
- CRM/Product/Shopping/Site/Feedback/Marketing adapters complete
- Event timeline access complete
- Agent’s first multi-service investigation works

### Milestone C: Domain intelligence operational
- Customer, Product, Digital, Promotion, and Voice-of-Customer agents produce valid answers
- Orchestrator routes correctly
- Evidence validation is active

### Milestone D: Governed analytics and graph
- Semantic metric catalog exists
- Graph relationships are populated and queryable
- KPI answers are consistent with service data

### Milestone E: Executive decision layer
- Decision briefs render with evidence, confidence, and next steps
- Human-in-the-loop checks are in place
- Follow-up questions are supported

---

## 7. Risks and Mitigations

### Risk: Agent hallucinates metrics or definitions
Mitigation:
- require metric definitions before analytical queries
- use semantic layer lookups first
- block unsupported claims

### Risk: Unauthorized access or over-broad retrieval
Mitigation:
- permission-check tool required before service/tool execution
- scope by principal, role, and domain
- fail closed on ambiguity

### Risk: Contradictory evidence across services
Mitigation:
- evidence validator compares sources
- mark contradiction explicitly
- avoid single-source causal statements

### Risk: Over-engineering before value is proven
Mitigation:
- deliver a minimal agent loop first
- add graph, RAG, and semantic layers iteratively
- validate with a handful of executive questions

---

## 8. First Target Questions for Validation

The first end-to-end validation set should include these prompts:

1. “Which customer segments responded best to the latest campaign?”
2. “Why did cart abandonment increase for mobile users this week?”
3. “Which products are underperforming relative to forecast?”
4. “Did the new promotion increase revenue or only traffic?”
5. “What customer issues are correlated with lower repeat purchase rates?”
6. “Which site or region is showing the strongest conversion trend?”

These questions exercise the core layers: metrics, services, graph, RAG, and decision synthesis.

---

## 9. Recommended Next Immediate Steps

1. Finalize the runtime contracts in `Agent/DecisionOS/runtime/`
2. Add service-adapter wrappers for CRM, Product, Shopping, Site, and Events
3. Implement the first orchestrator flow for a business question
4. Define the initial metric catalog for revenue, conversion, churn, and campaign uplift
5. Build the first two domain agents: `digital-intelligence` and `customer-intelligence`
6. Write focused tests for permission, evidence validation, and multi-step orchestration

---

## 10. Success Criteria

The agentic layer is considered successfully implemented when:

- the orchestration engine can handle multi-step executive investigations
- agents operate through governed tools only
- service and analytics responses are grounded in evidence
- metrics and business terms are governed and defined
- graph and RAG provide supporting context without dominating the answer
- final decision briefs are concise, auditable, and usable by executives

This marks the transition from an operational enterprise foundation to a true Enterprise Intelligence Brain capable of investigation, reasoning, and evidence-backed decision support.
