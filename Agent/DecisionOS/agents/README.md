# DecisionOS Agents

Agents are bounded runtime roles that compose prompts, skills, tools, memory, and persistence.

## Agent contract

Every agent must define:

- Mission and decision scope
- Prompt(s) it uses
- Skills it may invoke
- Tools it may call
- Memory it may read or write
- Required inputs and output contract
- Escalation and refusal rules

Agents do not receive unrestricted database access. All data access goes through governed tools and permission checks.

## Execution model

```text
User question
    |
    v
Executive Orchestrator
    |
    +--> Domain specialist agents
    |       |
    |       +--> governed tools
    |       +--> scoped memory
    |
    +--> Evidence Validator
    |
    +--> Decision Recorder
    |
    v
Evidence-backed decision brief
```

The Memory Steward manages durable memory policy. The Evidence Validator checks claims before the orchestrator can produce a final answer.
