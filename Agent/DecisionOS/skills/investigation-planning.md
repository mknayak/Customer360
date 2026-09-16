# Investigation Planning Skill

## Purpose

Turn an executive question into a bounded, testable investigation plan.

## Procedure

1. Restate the decision being supported.
2. Extract entities, metrics, dimensions, time period, baseline, and desired action.
3. Resolve terms through the semantic layer.
4. Identify the minimum evidence needed to answer the question.
5. Select specialist prompts and governed tools.
6. Define validation checks before retrieval.
7. Define what would count as an inconclusive result.

## Guardrails

- Do not plan tools that exceed the user's permissions.
- Do not request every data source by default.
- Do not turn an ambiguous question into an unstated assumption.
- Prefer a smaller reproducible investigation over a broad unsupported narrative.

## Completion criteria

The plan names the question, scope, sources, tools, calculations, permission checks, validation checks, and expected output.
