# Customer360 Domain Pack

Customer360 is the first DecisionOS domain pack. It supplies enterprise retail and customer-intelligence capabilities to the generic core.

## Domain scope

- Customer identity, profile, segment, retention, and frequency
- Products, categories, pricing, and promotions
- Carts, orders, payments, and shopping journeys
- Sites, visits, websites, and digital funnels
- Feedback, sentiment, complaints, and themes
- Campaigns, audiences, and channels
- Revenue, margin, conversion, and promotion economics

## Existing capability mapping

The current domain assets remain in the compatibility paths below while the runtime integration is built:

- Agents: `../../agents/`
- Prompts: `../../prompts/`
- Skills: `../../skills/`
- Tool specifications: `../../tools/`
- Memory and persistence policies: `../../memory/` and `../../persistence/`

## Pack responsibilities

The Customer360 pack must provide adapters for the CRM, Product, Shopping, Site, Feedback, Marketing, simulation, analytics, graph, and RAG systems. It owns domain metrics, entity mappings, source ownership, and evaluation scenarios.

It must not contain generic investigation lifecycle logic, permission middleware, or core persistence behavior.
