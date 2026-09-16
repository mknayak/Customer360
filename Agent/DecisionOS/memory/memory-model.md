# DecisionOS Memory Model

## Working memory

```text
InvestigationContext
- investigation_id
- conversation_id
- user_id
- question
- resolved_entities
- metric_definitions
- time_scope
- investigation_plan
- tool_results
- open_assumptions
- validation_status
- expires_at
```

Working memory may contain temporary evidence references and intermediate reasoning, but it must expire after the investigation or configured timeout.

## Conversation memory

```text
ConversationMemory
- memory_id
- user_id
- workspace_id
- type
- content_or_reference
- consent_status
- sensitivity
- source
- created_at
- expires_at
- version
```

Only explicit preferences, approved context, and useful follow-up references should be retained by default.

## Decision memory

```text
DecisionMemory
- decision_id
- investigation_id
- question
- decision_summary
- facts
- assumptions
- recommendations
- evidence_references
- confidence
- owner
- status
- review_date
- outcome
- created_at
- updated_at
```

A decision record must preserve the evidence references and metric definitions used to create it.

## Semantic memory

Semantic memory contains versioned, approved definitions and organizational knowledge. It must have an owner, effective dates, source references, and a review process.
