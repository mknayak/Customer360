# analytics.query

## Purpose

Execute a bounded, read-only query against curated analytical data.

## Required inputs

```text
metric_ids
entity_filters
time_period
comparison_period
dimensions
user_context
```

For dynamic analysis, callers submit a constrained semantic query IR rather
than SQL. The IR identifies a catalog metric, approved dimensions and filters,
sort direction, and row limit. Physical models, joins, expressions, and SQL are
selected and compiled by the Data Platform.

## Validation

- All metrics resolve through `semantic.lookup`.
- The requested scope is permitted by `permission.check`.
- The query has an explicit time range and row limit.
- The query is read-only.
- Caller-provided SQL, table names, expressions, and join clauses are rejected.
- Currency and time zone are explicit where relevant.

## Output

Return values, dimensions, query metadata, metric definitions, source tables, freshness, data-quality warnings, and a reproducible query reference.
