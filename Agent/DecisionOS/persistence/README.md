# DecisionOS Persistence

Persistence stores the durable records needed to resume investigations, explain decisions, and audit agent behavior.

## Logical stores

- `investigation_store`: questions, plans, state transitions, and tool results
- `decision_store`: approved decision briefs, actions, outcomes, and review history
- `evidence_store`: immutable references to source data, documents, queries, and graph versions
- `memory_store`: user, workspace, semantic, and working-memory records
- `audit_store`: authorization decisions, prompt versions, tool calls, writes, and deletions

These may initially be implemented in one PostgreSQL database with separate schemas. They remain separate logical ownership boundaries so they can be split later.

## Persistence principles

- Store references and metadata rather than duplicating operational facts.
- Use append-only records for audit and evidence provenance.
- Version prompts, metric definitions, decisions, and memory updates.
- Support idempotent writes using request and investigation IDs.
- Enforce tenant, workspace, user, and sensitivity boundaries at query time.
- Make retention, deletion, and export explicit operations.
