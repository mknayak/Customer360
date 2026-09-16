# permission.check

## Purpose

Determine whether a user may access a requested entity, metric, document, field, aggregation, or action.

## Required inputs

```text
user_context
requested_resources
requested_action
requested_scope
```

## Output

Return allow or deny per resource, applicable row and field filters, masking rules, aggregation thresholds, policy version, and audit reference.

Unknown or unavailable authorization must return `deny`, never `allow`.
