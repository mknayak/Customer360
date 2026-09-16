# Analytical Querying Skill

## Purpose

Compute quantitative facts from governed analytical data.

## Procedure

1. Translate the approved metric definition into a query plan.
2. Apply authorization filters before execution.
3. Select the appropriate grain and aggregation.
4. Calculate baseline, comparison, and relevant breakdowns.
5. Run data quality checks for duplicates, missing periods, outliers, and reconciliation.
6. Return the query, parameters, result, freshness, and warnings.

## Guardrails

- Use SQL or an approved analytical engine for numerical claims.
- Do not use vector similarity or LLM estimation for exact metrics.
- Do not hide failed queries or partial results.
- Keep the query read-only unless an explicitly approved action tool is selected.
