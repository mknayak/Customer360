# rag.search

## Purpose

Retrieve authorized passages from enterprise documents such as campaign briefs, finance policies, release notes, and customer research.

## Required inputs

```text
query
principal_id
entities
date_filters
source_filters
user_context
```

## Validation

- Document permissions are checked before retrieval.
- Results include document ID, title, version, author, date, and passage location.
- Retrieval scores are not treated as truth scores.
- Outdated or superseded documents are clearly marked.
- Retrieval is bounded by a result limit and document authorization.
- Graph context is returned as relationship evidence when an entity scope is provided.

## Output

Return passages, metadata, retrieval rationale, document freshness, and conflicts with other sources.
