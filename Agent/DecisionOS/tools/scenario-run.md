# scenario.run

## Purpose

Run a controlled business simulation scenario for deterministic DecisionOS evaluation.

## Required inputs

```text
scenario_id
parameters
start_time
end_time
seed
```

## Validation

- The scenario is registered and approved.
- The random seed is captured.
- Generated records are marked synthetic.
- The run is isolated from production data.
- The expected outcome is stored separately from agent-visible data.

## Output

Return run ID, generated dataset references, event counts, scenario metadata, seed, and expected evaluation reference.
