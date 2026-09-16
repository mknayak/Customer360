# decision.record

## Purpose

Persist an evidence-backed decision brief and its follow-up lifecycle.

## Required inputs

```text
user_context
investigation_id
decision_brief
evidence_ids
owner
status
review_date
```

## Validation

- The investigation is complete or explicitly marked partial.
- Every material claim has evidence or is labeled as a hypothesis.
- Evidence references are authorized and immutable.
- The decision owner and review date are present.
- A new version is created for updates.

## Output

Return decision ID, version, status, evidence references, review date, and audit reference.
