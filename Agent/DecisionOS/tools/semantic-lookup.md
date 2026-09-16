# semantic.lookup

## Purpose

Resolve business terms, metric definitions, source mappings, calculation rules, owners, and classifications.

## Required inputs

```text
terms
context
user_context
```

## Output

Return the canonical term, definition, formula, numerator, denominator, exclusions, sources, owner, grain, currency, time zone, security classification, version, and effective dates.

If multiple definitions match, return the alternatives and require the orchestrator to resolve the ambiguity.
