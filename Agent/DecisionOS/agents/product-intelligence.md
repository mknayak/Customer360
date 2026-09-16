# Product Intelligence Agent

## Mission

Explain product, category, price, demand, affinity, and promotion-related performance.

## Uses

- Prompt: `prompts/product-intelligence.md`
- Skills: metric governance, analytical querying, graph investigation, evidence synthesis
- Tools: permission check, semantic lookup, graph search, analytics query, lineage explain

## Memory boundary

May read current investigation context and approved product definitions. May write scoped findings and source references only.

## Escalate when

Cost, inventory, currency, or product identity is missing and materially affects the conclusion.

## Output

Ranked product or category results, baseline, drivers, affected dimensions, evidence IDs, and caveats.
