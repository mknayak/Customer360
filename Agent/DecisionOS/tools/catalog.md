# DecisionOS Tool Catalog

Tools are governed capabilities, not unrestricted access. Every tool must enforce authorization, return source metadata, and expose failures.

## Tool lifecycle

1. Check user permissions.
2. Validate the input schema.
3. Execute with bounded scope and timeout.
4. Return data plus provenance and freshness.
5. Log the request, decision, and result status.

## Tools

| Tool | Resource | Purpose | Read/Write |
|---|---|---|---|
| `customer.snapshot` | customer | Retrieve an authorized cross-service customer snapshot | Read |
| `analytics.query` | analytics | Execute a governed analytical query | Read |
| `analytics.segment` | analytics | Compare a metric by approved segment | Read |
| `analytics.funnel` | analytics | Calculate an approved funnel | Read |
| `analytics.compare_periods` | analytics | Compare a metric across periods | Read |
| `semantic.lookup` | semantic | Resolve a governed business term | Read |
| `semantic.metric_definition` | semantic | Retrieve a metric definition | Read |
| `semantic.entity_mapping` | semantic | Resolve an entity identifier | Read |
| `graph.search` | graph | Search approved entity relationships | Read |
| `graph.neighbors` | graph | Retrieve approved entity neighbors | Read |
| `graph.paths` | graph | Find an approved relationship path | Read |
| `graph.relationship_summary` | graph | Summarize entity relationships | Read |
| `rag.search` | rag | Retrieve authorized document passages | Read |
| `rag.document_lookup` | rag | Retrieve an authorized document | Read |
| `rag.policy_retrieve` | rag | Retrieve an authorized policy | Read |
| `permission.check` | governance | Check access to a resource | Read |
| `decision.evaluate` | governance | Evaluate decision claims and evidence | Read |
| `decision.record` | governance | Create a validated evidence-backed decision record | Read |
| `lineage.explain` | governance | Explain source and freshness metadata | Read |

No write tool should be enabled for executive investigation until approval, audit, and rollback behavior are defined.
