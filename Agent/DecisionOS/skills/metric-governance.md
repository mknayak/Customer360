# Metric Governance Skill

## Purpose

Ensure every quantitative claim uses an approved definition and reproducible calculation.

## Procedure

1. Look up the metric in the semantic layer.
2. Confirm owner, source, grain, filters, exclusions, currency, and time zone.
3. Confirm numerator, denominator, and null handling.
4. Confirm the comparison baseline.
5. Reject calculations when required inputs are missing or unauthorized.
6. Attach the definition and query metadata to the evidence record.

## Guardrails

- Never infer a metric definition from its name alone.
- Never compare values with incompatible scopes or denominators.
- Label estimates and forecasts distinctly from actuals.
- Report freshness and data completeness with the result.
