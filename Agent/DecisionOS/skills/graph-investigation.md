# Graph Investigation Skill

## Purpose

Use the knowledge graph to discover relevant entities, relationships, ownership, lineage, and context.

## Procedure

1. Resolve user terms to graph entity types and IDs.
2. Start from the smallest relevant subgraph.
3. Traverse only approved relationship types and depth.
4. Record source-system IDs for every material entity.
5. Hand high-volume facts to analytics tools instead of expanding them into the graph.
6. Return relationship evidence separately from numerical evidence.

## Guardrails

- Do not treat graph presence as proof of business performance.
- Do not infer causality from a relationship edge.
- Stop traversal when permissions, freshness, or entity identity is uncertain.
