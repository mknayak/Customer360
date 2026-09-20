# Scenario Engine

`scenario_engine.py` generates deterministic Customer360 datasets without external dependencies.

The default configuration generates 10,000 customers, 100 products, 5 sites, and 10,000 correlated journeys. Supported behavior modes are:

- `normal`
- `promotion_uplift`
- `website_degradation`
- `product_surge`
- `feedback_spike`

Generate a scenario file with:

```text
.venv/bin/python Enterprise/Simulator/scenario_engine.py \
  --output /tmp/customer360-scenario.json \
  --scenario promotion_uplift \
  --seed 42
```

Each journey includes a stable correlation ID and ordered event envelopes. Use a fixed seed to reproduce the same dataset for evaluation.
