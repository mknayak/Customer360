# DecisionOS Tool Catalog

Tools are governed capabilities, not unrestricted access. Every tool must enforce authorization, return source metadata, and expose failures.

## Tool lifecycle

1. Check user permissions.
2. Validate the input schema.
3. Execute with bounded scope and timeout.
4. Return data plus provenance and freshness.
5. Log the request, decision, and result status.

## Tools

| Tool | Purpose | Read/Write |
|---|---|---|
| `permission.check` | Resolve user and data access | Read |
| `semantic.lookup` | Resolve metric and business-term definitions | Read |
| `graph.search` | Traverse approved entity relationships | Read |
| `analytics.query` | Execute governed read-only analytical queries | Read |
| `rag.search` | Retrieve relevant documents and passages | Read |
| `lineage.explain` | Explain source, transformation, and freshness | Read |
| `feedback.aggregate` | Aggregate feedback themes and sentiment | Read |
| `scenario.run` | Generate controlled simulator behavior | Write |
| `decision.evaluate` | Score a decision brief against expectations | Read |
| `memory.retrieve` | Retrieve authorized DecisionOS memory | Read |
| `memory.store` | Persist approved memory with retention metadata | Write |
| `decision.record` | Persist a versioned evidence-backed decision | Write |

No write tool should be enabled for executive investigation until approval, audit, and rollback behavior are defined.
