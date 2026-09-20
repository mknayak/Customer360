# DecisionOS Tool Contract

Every tool specification must define:

```text
Name:
Purpose:
Owner:
Risk level:
Read/write mode:
Required permission:
Input schema:
Validation rules:
Execution limits:
Output schema:
Provenance fields:
Failure behavior:
Audit fields:
```

## Common output envelope

```json
{
  "status": "succeeded | partial | failed | denied",
  "data": {},
  "source": [],
  "definition": [],
  "filters": {},
  "freshness": {},
  "warnings": [],
  "request_id": "string",
  "generated_at": "timestamp",
  "query_metadata": {},
  "evidence_references": []
}
```

Tools must fail closed for authorization errors and must never return unmarked synthetic or estimated values as actual enterprise facts.
