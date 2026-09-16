# DecisionOS Memory

DecisionOS memory is governed state used to make investigations coherent across turns and useful across time. It is not an unrestricted transcript store.

## Memory types

| Type | Lifetime | Purpose | Default sensitivity |
|---|---|---|---|
| Working memory | One investigation | Current question, plan, entities, tool results, and unresolved assumptions | Restricted |
| Conversation memory | User or executive workspace | Preferences, prior questions, and approved follow-up context | Restricted |
| Decision memory | Durable | Decision briefs, outcomes, actions, and later results | Confidential |
| Semantic memory | Durable | Approved business definitions, policies, playbooks, and lessons | Governed |
| Audit memory | Retention policy | Access, tool calls, approvals, and changes | Restricted |

## Rules

- Store only the minimum information needed for continuity or governance.
- Store references to source data instead of copying large datasets into memory.
- Apply authorization on every memory read and write.
- Record consent and retention metadata for user-specific memory.
- Never store secrets, credentials, or unrestricted PII in prompts or memory.
- Mark synthetic, estimated, and production evidence explicitly.
- Allow correction, export, and deletion according to policy.
