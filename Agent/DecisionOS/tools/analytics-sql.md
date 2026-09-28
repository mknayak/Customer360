# analytics.sql

## Purpose

Answer analytical questions that the metric catalog (`analytics.query`) cannot
express by letting the model write SQL against a pruned, authorized schema.

## Inputs

```text
question
principal_id
```

## Flow

1. `POST /api/sql/context`: the Data Platform returns only tables in the
   principal's domains, selected by vector search, join-path linking and
   business-rule injection, with column descriptions, sample values, row counts
   and null ratios.
2. The model returns `{"answerable", "sql", "assumptions", "reason"}`.
3. `POST /api/sql/execute` validates and runs the SQL read-only. Validation or
   SQL errors are sent back to the model for repair, up to 3 attempts.
4. The model phrases the answer only from returned rows and cites `sql:<query_id>`.

## Boundaries

- Read-only; one `SELECT`/`WITH` statement; row cap and time budget.
- Authorization fails closed before retrieval and at execution (SQLite authorizer).
- If the schema lacks the needed data, the tool returns `unanswerable` and no
  substitute metric is used.
- Trend and CRM-profile questions stay on `analytics.query`.
- Enabled only when an LLM provider is configured; disable with
  `SQL_AGENT_ENABLED=false`. On failure the brief falls back to `analytics.query`.

## Output

Status, SQL, columns, rows, assumptions, attempts with errors, context tables,
applied business rules, tables read, freshness, and query ID.
