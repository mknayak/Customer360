# memory.retrieve

## Purpose

Retrieve authorized DecisionOS memory relevant to the current investigation.

## Required inputs

```text
user_context
memory_types
subject_ids
query
workspace_scope
```

## Validation

- `permission.check` succeeds before retrieval.
- Memory is within retention and consent scope.
- Sensitivity and workspace filters are applied at the store.
- Expired or deleted records are excluded.
- Results include memory type, source, version, and freshness.

## Output

Return relevant memory references and content with provenance, authorization scope, expiry, and warnings. Never return hidden reasoning or restricted records.
