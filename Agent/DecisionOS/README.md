# DecisionOS

DecisionOS is the prompt and decision-governance layer for the Enterprise Intelligence Brain.

It converts an executive question into a bounded investigation, delegates work to specialist capabilities, and returns an evidence-backed decision brief.

## Design rules

- Treat the LLM as an investigator, not a system of record.
- Use analytics for numerical facts and calculations.
- Use the knowledge graph for entities, relationships, and business context.
- Use RAG for policies, briefs, reports, and other documents.
- Never invent missing data, definitions, permissions, or causal explanations.
- Preserve source attribution, filters, time periods, and data freshness.
- Apply authorization before retrieval and tool execution.
- Separate observed facts, interpretations, hypotheses, and recommendations.

## Prompt layout

```text
DecisionOS/
|-- README.md
|-- core/
|   |-- README.md
|   |-- contracts.md
|-- domains/
|   |-- customer360/
|       |-- README.md
|       |-- registry.md
|-- agents/
|   |-- README.md
|   |-- registry.md
|   |-- executive-orchestrator.md
|   |-- customer-intelligence.md
|   |-- product-intelligence.md
|   |-- promotion-intelligence.md
|   |-- digital-intelligence.md
|   |-- voice-of-customer.md
|   |-- finance-intelligence.md
|   |-- evidence-validator.md
|   |-- memory-steward.md
|-- prompts/
|   |-- executive-orchestrator.md
|   |-- customer-intelligence.md
|   |-- product-intelligence.md
|   |-- promotion-intelligence.md
|   |-- digital-intelligence.md
|   |-- voice-of-customer.md
|   |-- finance-intelligence.md
|   |-- decision-evaluator.md
|-- skills/
|   |-- investigation-planning.md
|   |-- metric-governance.md
|   |-- graph-investigation.md
|   |-- analytical-querying.md
|   |-- evidence-synthesis.md
|   |-- permission-safety.md
|   |-- scenario-evaluation.md
|-- memory/
|   |-- README.md
|   |-- memory-model.md
|   |-- memory-policy.md
|-- persistence/
|   |-- README.md
|   |-- schema.md
|-- runtime/
|   |-- README.md
|   |-- pyproject.toml
|   |-- decision_os/
|   |-- tests/
|-- tools/
	|-- catalog.md
	|-- tool-contract.md
	|-- permission-check.md
	|-- semantic-lookup.md
	|-- graph-search.md
	|-- analytics-query.md
	|-- rag-search.md
	|-- lineage-explain.md
	|-- scenario-run.md
	|-- decision-evaluate.md
	|-- memory-retrieve.md
	|-- memory-store.md
	|-- decision-record.md
```

## Skills and tools

Skills define reusable reasoning procedures such as investigation planning, metric governance, analytical querying, evidence synthesis, permission safety, and scenario evaluation.

Tools define bounded capabilities such as semantic lookup, graph search, analytics queries, document retrieval, lineage inspection, permission checks, simulation, and decision evaluation. Tools must follow the contract in `tools/tool-contract.md` and be listed in `tools/catalog.md`.

Skills may recommend tools, but they must not bypass tool authorization or treat tool output as trustworthy without provenance.

## Core and domain packs

DecisionOS Core is application- and industry-agnostic. It owns the runtime lifecycle, contracts, permission enforcement, evidence rules, persistence interfaces, memory governance, and evaluation boundaries. See `core/`.

Domain packs supply the business-specific agents, prompts, skills, tools, metrics, entity mappings, data adapters, and evaluation scenarios. Customer360 is the first domain pack. See `domains/customer360/`.

The existing top-level agents, prompts, skills, and tools remain the compatibility surface while the runtime integration is developed. New generic capabilities belong in `core/`; Customer360-specific capabilities belong in `domains/customer360/`.

## Agents

Agents are bounded runtime roles that compose prompts, skills, tools, memory, and persistence. The `executive-orchestrator` plans and delegates investigations; domain agents analyze specific business areas; the `evidence-validator` checks claims before the final response; and the `memory-steward` governs durable memory lifecycle operations.

The complete agent scope, tool access, memory boundaries, and escalation rules are defined in `agents/registry.md`.

## Memory and persistence

Memory is split into working, conversation, decision, semantic, and audit memory. Working memory supports the current investigation; durable memory requires source, sensitivity, retention, and authorization metadata. See `memory/memory-policy.md`.

Persistence stores investigations, decisions, evidence references, memory records, and audit events as separate logical stores. The initial implementation may use PostgreSQL schemas, but evidence and audit records remain append-only and durable decisions remain versioned. See `persistence/schema.md`.

## Runtime foundation

`runtime/` contains the first executable slice: typed contracts, permission-first tool dispatch, investigation lifecycle state, replaceable persistence, and deterministic decision evaluation. It is dependency-free at runtime and currently uses an in-memory persistence adapter. Enterprise, database, LLM, graph, and RAG adapters will be added behind these contracts.

## Standard input

Every prompt should receive:

- The user's question
- User role and permissions
- Relevant entities and identifiers
- Time period and comparison period
- Available tools
- Metric definitions
- Retrieved evidence
- Data freshness and completeness

## Standard output

Every decision brief should contain:

1. Decision or question addressed
2. Direct answer
3. Observed facts and metrics
4. Key drivers and relationships
5. Confidence and limitations
6. Evidence and lineage
7. Recommended next actions
8. Follow-up questions

The prompts are implementation specifications. They should be wired to governed tools before being used with production or synthetic enterprise data.
