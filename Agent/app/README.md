# Agent Application Shell

This package is the execution layer for the Customer360 agentic runtime.

It deliberately keeps the DecisionOS runtime as the brain and governance layer, while the app package implements the concrete runtime behavior:

- API entrypoints
- tool implementations
- service adapters
- investigation orchestration
- permission-aware execution paths

## Current state

This is the first scaffold for Phase 1 of the agentic plan. It exposes a minimal FastAPI app that:

- creates an investigation
- plans an investigation
- executes governed catalog tools
- reaches read-only enterprise services through DecisionOS adapters
- advances the lifecycle state

## Next steps

- add a domain agent orchestration layer
- add persisted evidence and decision records
- add richer permission checks by role and resource
- add model-backed reasoning paths behind the tool layer
