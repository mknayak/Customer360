# DecisionOS Core Contracts

These contracts are the stable integration boundary between the generic runtime and domain packs.

## Domain pack registration

```text
DomainPack
- pack_id
- name
- version
- description
- agents
- skills
- tools
- metric_definitions
- entity_types
- relationship_types
- permission_policy
- evaluation_scenarios
```

## Capability registration rules

- Names are namespaced by pack, for example `customer360.analytics.query`.
- Tool handlers must use the runtime tool contract.
- Agents must declare their allowed tools and memory boundaries.
- Metric definitions must include owner, source, grain, formula, exclusions, and effective dates.
- Every domain capability must provide failure and authorization behavior.
- Pack versions must be recorded with every investigation and decision.

## Compatibility

Core changes require contract tests against every registered domain pack. Domain packs may evolve independently when they preserve the core contracts.
