# DecisionOS Runtime Foundation

This directory contains the first executable DecisionOS slice. It is intentionally dependency-free and uses an in-memory persistence adapter until the enterprise services and PostgreSQL schema are available.

## Components

- `decision_os.models`: typed investigation, tool, permission, evidence, and decision contracts
- `decision_os.tools`: permission-first tool registration and dispatch
- `decision_os.engine`: investigation lifecycle state machine
- `decision_os.persistence`: replaceable persistence protocol and in-memory adapter
- `decision_os.evaluation`: deterministic claim evaluation primitives
- `tests/`: focused runtime behavior tests

## Run tests

From this directory:

```text
python -m pytest
```

The runtime does not call LLMs or enterprise systems yet. Adapters can be added behind the typed ports once the service contracts are implemented.
