# memory.store

## Purpose

Persist approved working, conversation, decision, or semantic memory.

## Required inputs

```text
user_context
memory_type
subject_id
content_or_reference
purpose
sensitivity
retention
consent_status
source
request_id
```

## Validation

- The memory type is allowed for automatic or approved writes.
- Secrets and unsupported conclusions are rejected.
- Source and sensitivity are present.
- Retention and deletion behavior are defined.
- The write is idempotent by request ID.
- Authorization and consent are recorded.

## Output

Return memory ID, version, status, retention date, audit reference, and any redaction warnings.
