# Scenario Evaluation Skill

## Purpose

Test whether DecisionOS reaches known conclusions from controlled simulator scenarios.

## Procedure

1. Load the scenario identifier and expected business change.
2. Ask the target executive question without exposing the expected answer.
3. Capture the plan, tool calls, calculations, evidence, and final brief.
4. Compare discovered facts with scenario truth.
5. Score intent, retrieval, calculations, attribution, permissions, and usefulness.
6. Record false positives, missed drivers, and unsupported claims.

## Example expectation

If a scenario increases transactions by 20 percent and reduces margin by 5 percent, the system should report transaction growth and margin decline separately. It must not summarize the scenario as an unqualified success.
