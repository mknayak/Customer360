# Permission Safety Skill

## Purpose

Prevent agents from retrieving or exposing data beyond the requesting user's authority.

## Procedure

1. Resolve the user identity, role, tenant, and permitted scopes.
2. Check access before planning retrieval and again before tool execution.
3. Apply row, column, document, and aggregation restrictions at the source.
4. Mask or omit restricted identifiers and sensitive attributes.
5. Prevent inference of protected data from small groups or combined outputs.
6. Record the authorization decision and denied sources.

## Guardrails

- Never rely on the final response layer to enforce access.
- Never reveal whether a restricted record exists unless permitted.
- Fail closed when authorization status is missing or ambiguous.
