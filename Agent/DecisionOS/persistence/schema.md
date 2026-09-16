# DecisionOS Persistence Schema

## Core records

```text
conversation
- conversation_id, user_id, workspace_id, status, created_at, updated_at

investigation
- investigation_id, conversation_id, question, plan, status, prompt_version
- started_at, completed_at, created_by

evidence_reference
- evidence_id, investigation_id, source_type, source_id, query_reference
- definition_version, source_version, freshness, content_hash, access_scope

decision_record
- decision_id, investigation_id, summary, facts, assumptions, recommendations
- confidence, owner, status, review_date, created_at, updated_at

memory_record
- memory_id, memory_type, subject_id, content_or_reference, sensitivity
- consent_status, source, version, expires_at, deleted_at

audit_event
- audit_id, user_id, investigation_id, action, resource, result
- policy_version, request_id, occurred_at
```

## Integrity requirements

- `evidence_reference` records are immutable.
- `decision_record` updates create a new version.
- `memory_record` writes are idempotent by subject and request ID.
- Deleted memory remains represented by a tombstone in the audit trail.
- Every durable decision must reference at least one investigation and its evidence.
