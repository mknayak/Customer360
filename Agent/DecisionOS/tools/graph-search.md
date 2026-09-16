# graph.search

## Purpose

Find entities and approved relationships in the enterprise knowledge graph.

## Required inputs

```text
start_entities
relationship_types
max_depth
filters
user_context
```

## Validation

- Entity IDs are resolved or explicitly marked as ambiguous.
- Traversal depth and result count are bounded.
- Relationship types are on the approved allowlist.
- Permission checks are complete before traversal.

## Output

Return entities, edges, source-system IDs, relationship provenance, graph version, freshness, omitted restricted results, and warnings.
