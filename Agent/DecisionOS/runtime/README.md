# DecisionOS Runtime Foundation

This directory contains the first executable DecisionOS slice. It is intentionally dependency-free and uses an in-memory persistence adapter until the enterprise services and PostgreSQL schema are available.

## Components

- `decision_os.models`: typed investigation, tool, permission, evidence, and decision contracts
- `decision_os.catalog`: allow-listed tool contracts and handler registration
- `decision_os.adapters`: read-only service clients, domain adapters, and multi-hop retrieval
- `decision_os.tools`: permission-first tool registration and dispatch
- `decision_os.engine`: investigation lifecycle state machine
- `decision_os.persistence`: replaceable persistence protocol and in-memory adapter
- `decision_os.evaluation`: deterministic claim evaluation primitives
- `decision_os.semantic`: versioned Customer360 metric definitions and governed lookup
- `decision_os.graph`: allowlisted entity schema, refresh API, bounded relationship traversal, and graph tool handlers
- `tests/`: focused runtime behavior tests

Graphs can be rendered in Markdown-compatible viewers without an additional dependency:

```python
from decision_os.graph import GraphStore

graph = GraphStore()
graph.sync(entities, relationships)
print(graph.to_mermaid())
```

The export is deterministic, bounded, and preserves relationship direction and labels.

## Run tests

From this directory:

```text
python -m pytest
```

The runtime does not call LLMs or enterprise systems yet. Semantic lookups are resolved from the approved in-process metric registry, and graph records are refreshed through the typed `GraphStore.sync` port. Persistent graph and service-specific refresh jobs can be added behind these ports without changing governed tool callers.
