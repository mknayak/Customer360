# Enterprise Services

These services own the synthetic enterprise's operational data and APIs. Each
service must keep its persistence boundary private and communicate with other
services through identifiers, APIs, and domain events.

## Shared environment

All services use the repository-root virtual environment:

```text
source .venv/bin/activate
```

Services should not create separate virtual environments inside their service
directories.

## Services

| Service | Owns | Initial event examples |
|---|---|---|
| `crm` | Customers, profiles, and segments | `CustomerCreated`, `CustomerUpdated`, `CustomerSegmentChanged` |
| `product` | Products, categories, prices, and promotions | `ProductCreated`, `PriceChanged`, `PromotionStarted` |
| `shopping` | Carts, orders, order items, and payments | `CartAbandoned`, `OrderCreated`, `PaymentCompleted` |
| `site` | Physical and digital sites plus visits | `SiteCreated`, `VisitStarted`, `VisitEnded` |
| `feedback` | Customer feedback and ratings | `FeedbackSubmitted`, `FeedbackUpdated` |
| `marketing` | Campaigns, audiences, and channels | `CampaignCreated`, `CampaignStarted`, `CampaignEnded` |

## Boundary rules

- A service owns its database and schema.
- Each service stores its SQLite database under its own `data/` directory.
- Database files use the service name, for example `crm/data/crm.sqlite3`.
- Cross-service relationships use IDs rather than shared tables.
- Cross-service joins belong in the data platform, not operational services.
- APIs validate their own domain invariants.
- Important business changes produce domain events.
- Service adapters must not access DecisionOS directly; DecisionOS will use
  governed tools over service and analytical interfaces.

## Planned layout

```text
Enterprise/Services/<service>/
|-- api/
|-- domain/
|-- persistence/
|-- tests/
|-- README.md
```

The first implementation slices are CRM, Product, Shopping, Feedback, and
Marketing. Site remains a planned service boundary.