# DecisionOS Agent Registry

| Agent | Scope | Primary prompt | Write access |
|---|---|---|---|
| `executive-orchestrator` | Plan and coordinate investigations | `prompts/executive-orchestrator.md` | Working memory, approved decision record |
| `customer-intelligence` | Retention, churn, segments, frequency, customer value | `prompts/customer-intelligence.md` | Working memory only |
| `product-intelligence` | Product, category, price, demand, affinity | `prompts/product-intelligence.md` | Working memory only |
| `promotion-intelligence` | Promotion effectiveness and economics | `prompts/promotion-intelligence.md` | Working memory only |
| `digital-intelligence` | Visits, funnels, checkout, conversion | `prompts/digital-intelligence.md` | Working memory only |
| `voice-of-customer` | Feedback themes, sentiment, complaints | `prompts/voice-of-customer.md` | Working memory only |
| `finance-intelligence` | Revenue, margin, cost, variance, forecast | `prompts/finance-intelligence.md` | Working memory only |
| `evidence-validator` | Validate claims, sources, freshness, and causality | `prompts/decision-evaluator.md` | Evaluation record |
| `memory-steward` | Govern memory retention, consent, and deletion | `memory/memory-policy.md` | Memory records with policy approval |

All agents use `tools/permission-check.md` before other tools. Domain agents cannot call write tools or modify operational enterprise data.
