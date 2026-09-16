# Customer360 Copilot Instructions

## Project context

This repository develops the Enterprise Intelligence Brain described in `enterprise-intelligence-brain-development.md`.

The intended sequence is bottom-up:

1. Synthetic enterprise services and databases
2. Business simulation and realistic events
3. Event and analytical platform
4. Semantic layer and knowledge graph
5. RAG and GraphRAG
6. Governed agent orchestration
7. Executive decision experience

Do not introduce chatbot behavior before the underlying data and evidence paths are coherent.

## DecisionOS

`Agent/DecisionOS/` is the agent governance layer. It contains:

- `agents/`: bounded runtime roles and their responsibilities
- `prompts/`: role-specific prompt instructions
- `skills/`: reusable reasoning procedures
- `tools/`: governed capability contracts
- `memory/`: memory types, lifecycle, consent, and retention policy
- `persistence/`: durable records, evidence references, and audit schema

When adding a DecisionOS capability, define its scope, inputs, outputs, allowed tools, memory boundary, permission requirements, failure behavior, and evidence expectations.

## Non-negotiable design rules

- Treat the LLM as an investigator, never as the system of record.
- Use analytics for numerical facts and calculations.
- Use the knowledge graph for entities and relationships.
- Use RAG for documents, policies, briefs, and unstructured context.
- Resolve business terms and metrics through the semantic layer.
- Apply authorization before retrieval and tool execution.
- Preserve source, query, definition, time period, filters, freshness, and request identifiers.
- Separate facts, interpretations, hypotheses, and recommendations.
- Do not claim causality from correlation alone.
- Do not store secrets, credentials, unrestricted PII, or hidden chain-of-thought in memory.
- Mark synthetic, estimated, forecast, and production data distinctly.
- Prefer small, reproducible changes over broad abstractions.

## Agent boundaries

Agents must use governed tools and must not access operational databases directly. Domain agents should write only scoped working findings with evidence references. Durable decisions require validation, ownership, review metadata, and versioning.

Write tools must fail closed on authorization errors and must be auditable. Missing permissions, ambiguous metric definitions, stale data, or contradictory sources must be surfaced rather than silently resolved.

## Documentation and implementation

Keep specifications close to the component they govern. Update the relevant DecisionOS registry or catalog when adding an agent, skill, or tool. Preserve existing public names and avoid unrelated refactoring.

Before reporting completion, run the narrowest available validation for the changed files and state any unimplemented runtime behavior clearly.
