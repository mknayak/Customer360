# Enterprise Intelligence Brain
## Development Architecture & Implementation Specification

**Status:** Development Blueprint  
**Purpose:** Build a synthetic enterprise data ecosystem first, then layer GraphRAG, analytics, and agentic AI on top.

---

## 1. Vision

Build an **Enterprise Intelligence Brain** that provides a unified conversational interface for executives such as CEOs and CFOs.

Users should be able to ask questions such as:

- How did the new promotion work?
- Are customer retention rates improving?
- Is the new website working as expected?
- Did sales revenue increase?
- Who are our most frequent visitors?
- Which products are hot-selling?
- Why are customers abandoning carts?
- What are customers complaining about?
- Which customer segments responded best to the campaign?
- Why did revenue decline in a particular site or region?

The system should act as an intelligent investigation layer across enterprise data.

### Core principle

> **Build the enterprise first. Build the brain second.**

The first phase will create a controlled synthetic enterprise using small, independently deployable microservices. These services provide APIs and databases that generate realistic business data.

The AI platform will later consume this data through events, APIs, analytical stores, semantic models, and a knowledge graph.

---

# 2. Architectural Philosophy

The solution separates five responsibilities:

| Layer | Responsibility |
|---|---|
| Microservices | Own operational business data and APIs |
| Data Platform | Store, transform, aggregate, and analyze facts |
| Knowledge Graph | Represent business entities and relationships |
| AI/Agent Layer | Understand questions, plan investigations, retrieve data, reason |
| Executive Experience | Present evidence-backed insights |

### Important distinction

The graph is **not** the primary database for every transaction and event.

Use:

- **Operational databases** for transactional service data.
- **Data warehouse/lakehouse** for high-volume facts and analytical queries.
- **Knowledge graph** for entities, relationships, business context, lineage, and semantic navigation.
- **Vector/RAG stores** for unstructured knowledge.
- **Analytics engines** for quantitative calculations.

---

# 3. Target Evolution

```text
Phase 1
  Microservices + Databases
          |
          v
Phase 2
  Business Simulation
          |
          v
Phase 3
  Event Backbone + Data Platform
          |
          v
Phase 4
  Semantic Layer + Knowledge Graph
          |
          v
Phase 5
  RAG + GraphRAG
          |
          v
Phase 6
  Agentic Orchestration
          |
          v
Phase 7
  Executive Intelligence Experience
```

---

# 4. Synthetic Enterprise

The initial enterprise should contain:

```text
CRM
Product
Shopping
Marketing
Feedback
Site / Location
Website 1 - Shopping Simulator
Website 2 - Content Site
Event Backbone
Business Simulation Engine
```

Additional services can be introduced later.

---

# 5. Microservice Architecture

Each service should follow:

```text
API
 |
Application / Domain Logic
 |
Persistence
 |
Database
```

Each service owns its own database.

### Rules

1. No shared operational database between services.
2. Services communicate through APIs and events.
3. Foreign relationships across services are represented by IDs.
4. Cross-service joins belong in the data/analytics layer.
5. Domain events should be emitted for important business actions.
6. CRUD APIs should remain intentionally simple in the first iteration.

---

# 6. CRM Microservice

## Responsibility

Store customer identity and basic customer profile information.

## Core entities

### Customer

```text
Customer
--------
customer_id
first_name
last_name
email
phone
status
created_at
updated_at
```

### CustomerProfile

```text
CustomerProfile
---------------
customer_id
age_group
city
country
preferred_channel
```

### CustomerSegment

```text
CustomerSegment
---------------
customer_id
segment
effective_from
effective_to
```

## Initial APIs

```http
POST   /api/customers
GET    /api/customers
GET    /api/customers/{id}
PUT    /api/customers/{id}
DELETE /api/customers/{id}

POST   /api/customers/{id}/profile
GET    /api/customers/{id}/profile
PUT    /api/customers/{id}/profile

POST   /api/customers/{id}/segments
GET    /api/customers/{id}/segments
```

## Events

```text
CustomerCreated
CustomerUpdated
CustomerSegmentChanged
```

---

# 7. Product Microservice

## Responsibility

Manage products, categories, pricing, and promotions.

## Core entities

### Product

```text
Product
-------
product_id
sku
name
description
category_id
brand
status
created_at
updated_at
```

### Category

```text
Category
--------
category_id
name
parent_category_id
```

### Price

```text
Price
-----
price_id
product_id
amount
currency
effective_from
effective_to
```

### Promotion

```text
Promotion
---------
promotion_id
name
description
discount_type
discount_value
start_date
end_date
status
```

### PromotionProduct

```text
PromotionProduct
----------------
promotion_id
product_id
```

## APIs

```http
POST   /api/products
GET    /api/products
GET    /api/products/{id}
PUT    /api/products/{id}
DELETE /api/products/{id}

POST   /api/categories
GET    /api/categories

POST   /api/products/{id}/prices
GET    /api/products/{id}/prices

POST   /api/promotions
GET    /api/promotions
GET    /api/promotions/{id}
PUT    /api/promotions/{id}
DELETE /api/promotions/{id}
```

## Events

```text
ProductCreated
ProductUpdated
PriceChanged
PromotionCreated
PromotionStarted
PromotionEnded
```

---

# 8. Shopping Microservice

## Responsibility

Represent customer shopping behavior and transactions.

## Core entities

```text
Cart
CartItem
Order
OrderItem
Payment
```

### Cart

```text
Cart
----
cart_id
customer_id
site_id
status
created_at
updated_at
```

### CartItem

```text
CartItem
--------
cart_item_id
cart_id
product_id
quantity
unit_price
```

### Order

```text
Order
-----
order_id
customer_id
site_id
promotion_id
total_amount
currency
status
created_at
```

### OrderItem

```text
OrderItem
---------
order_item_id
order_id
product_id
quantity
unit_price
discount_amount
```

## APIs

```http
POST   /api/carts
GET    /api/carts/{id}
PUT    /api/carts/{id}

POST   /api/carts/{id}/items
PUT    /api/carts/{id}/items/{itemId}
DELETE /api/carts/{id}/items/{itemId}

POST   /api/orders
GET    /api/orders
GET    /api/orders/{id}
PUT    /api/orders/{id}
```

## Events

```text
CartCreated
ProductAddedToCart
ProductRemovedFromCart
CartAbandoned
CheckoutStarted
OrderCreated
OrderCompleted
OrderCancelled
PaymentCompleted
PaymentFailed
```

---

# 9. Site / Location Microservice

## Responsibility

Represent physical and digital sites.

### Site

```text
Site
----
site_id
name
type
city
country
opened_date
status
```

Types:

```text
STORE
WEBSITE
MOBILE_APP
```

### Visit

```text
Visit
-----
visit_id
customer_id
site_id
channel
started_at
ended_at
```

## APIs

```http
POST /api/sites
GET  /api/sites
GET  /api/sites/{id}
PUT  /api/sites/{id}
DELETE /api/sites/{id}

POST /api/visits
GET  /api/visits
GET  /api/visits/{id}
```

## Events

```text
SiteCreated
VisitStarted
VisitEnded
```

---

# 10. Website 1 - Shopping Simulator

This is intentionally **not a full e-commerce application**.

Provide a single lightweight page that simulates:

```text
Visit
  |
Product View
  |
Add To Cart
  |
Checkout
  |
Payment
  |
Order
```

Alternative journeys:

```text
Visit -> Product View -> Exit

Visit -> Product View -> Add To Cart -> Cart Abandoned

Visit -> Product View -> Checkout -> Payment Failed

Visit -> Product View -> Purchase
```

The website should call the underlying microservices.

### Purpose

Generate realistic behavioral data for:

- traffic
- product views
- conversion
- funnel drop rates
- cart abandonment
- purchases
- payment failures
- promotion usage

---

# 11. Website 2 - Content Site

A simple static content site.

Example content:

```text
About
Products
News
Blog
Customer Stories
Sustainability
Company Information
```

Generate:

```text
PageVisit
ContentView
Search
TimeOnPage
Exit
```

This becomes the initial source for unstructured knowledge and RAG.

---

# 12. Feedback Microservice

## Responsibility

Store customer feedback.

### Feedback

```text
Feedback
--------
feedback_id
customer_id
site_id
source
rating
text
created_at
```

Possible sources:

```text
SURVEY
REVIEW
WEBSITE
SUPPORT
SOCIAL
```

## APIs

```http
POST   /api/feedback
GET    /api/feedback
GET    /api/feedback/{id}
PUT    /api/feedback/{id}
DELETE /api/feedback/{id}
```

## Events

```text
FeedbackSubmitted
FeedbackUpdated
```

Later AI processing can derive:

```text
Sentiment
Topic
Intent
ProductMention
SiteMention
ComplaintType
```

---

# 13. Marketing Microservice

## Responsibility

Represent campaigns and campaign audiences.

### Campaign

```text
Campaign
--------
campaign_id
name
description
start_date
end_date
status
```

### CampaignAudience

```text
CampaignAudience
----------------
campaign_id
segment
```

### CampaignChannel

```text
CampaignChannel
---------------
campaign_id
channel
```

Possible channels:

```text
EMAIL
SMS
WEB
SOCIAL
STORE
APP
```

## Events

```text
CampaignCreated
CampaignStarted
CampaignEnded
CampaignAudienceChanged
```

---

# 14. Event Backbone

Introduce an event backbone after the basic CRUD services are working.

```text
Microservices
     |
     | Domain Events
     v
+------------------+
| Event Backbone   |
+------------------+
     |
     +----> Data Platform
     |
     +----> Analytics
     |
     +----> Knowledge Graph
     |
     +----> Monitoring
```

Possible technologies:

- Kafka
- RabbitMQ
- AWS messaging/event services
- Azure messaging/event services

For the local MVP, choose the simplest technology that supports reliable event publishing and consumption.

---

# 15. Business Simulation Engine

This is a central component of the development environment.

It should generate realistic enterprise behavior.

## Responsibilities

```text
Generate customers
Generate products
Generate sites
Generate promotions
Generate visits
Generate product views
Generate carts
Generate orders
Generate feedback
Generate campaigns
Generate behavioral patterns
```

## Configurable scenarios

### Scenario 1 - Normal business

```text
Normal traffic
Normal conversion
Normal sales
Normal feedback
```

### Scenario 2 - Successful promotion

```text
Promotion launched
        |
Traffic increases
        |
Conversion increases
        |
Sales increase
        |
New customers increase
        |
Margin changes
```

### Scenario 3 - Website failure

```text
Website release
        |
Checkout failures increase
        |
Cart abandonment increases
        |
Conversion decreases
        |
Customer complaints increase
```

### Scenario 4 - New site launch

```text
New site opens
        |
Visitors increase
        |
Initial purchases increase
        |
Repeat visits remain weak
```

### Scenario 5 - Product surge

```text
Product becomes popular
        |
Views increase
        |
Purchases increase
        |
Inventory pressure increases
```

The simulator should allow scenario parameters to be changed deliberately so the AI can later be tested against known outcomes.

---

# 16. Data Platform

The data platform is where operational data becomes enterprise analytical data.

```text
Microservices
      |
      v
Event Backbone
      |
      v
Ingestion
      |
      v
Data Lake / Warehouse
      |
      +---- Raw
      +---- Cleansed
      +---- Curated
      +---- Analytical
```

Potential capabilities:

```text
Batch ingestion
Streaming ingestion
Transformation
Data quality
Data catalog
Data lineage
Aggregation
Analytics
```

The initial implementation can be much simpler than a production enterprise platform.

---

# 17. Enterprise Semantic Layer

The semantic layer defines what business terms mean.

Examples:

```text
Revenue
Sales
Customer
Active Customer
Retention
Conversion
Cart Abandonment
Promotion ROI
Gross Margin
Frequent Visitor
Hot Product
```

Example:

```text
Revenue
-------
Definition:
Recognized sales after defined exclusions.

Source:
Order / Finance data

Calculation:
SUM(eligible order amounts)

Owner:
Finance
```

This prevents the LLM from inventing definitions.

The semantic layer should also map business concepts to:

- source tables
- APIs
- metrics
- graph entities
- calculation rules
- data owners
- security classifications

---

# 18. Enterprise Knowledge Graph

The graph represents business entities and relationships.

## Example

```text
Customer
   |
   +-- belongs_to --> Segment
   |
   +-- visits --> Site
   |
   +-- views --> Product
   |
   +-- creates --> Cart
   |
   +-- purchases --> Product
   |
   +-- responds_to --> Promotion
   |
   +-- submits --> Feedback

Product
   |
   +-- belongs_to --> Category
   |
   +-- sold_at --> Site
   |
   +-- included_in --> Promotion

Promotion
   |
   +-- targets --> Segment
   |
   +-- promotes --> Product
   |
   +-- runs_at --> Site
```

## What belongs in the graph?

Good candidates:

```text
Business entities
Relationships
Business concepts
Hierarchy
Ontology
Data lineage
Metric definitions
Source relationships
Document relationships
```

Do not automatically create a graph node for every:

```text
timestamp
transaction amount
quantity
tax amount
click event
raw telemetry event
```

High-volume facts should normally remain in analytical stores.

---

# 19. GraphRAG

GraphRAG combines graph-based retrieval with LLM-based reasoning.

Traditional RAG:

```text
Question
   |
Embedding
   |
Vector Search
   |
Relevant chunks
   |
LLM
```

GraphRAG:

```text
Question
   |
Understand entities/concepts
   |
Graph traversal
   |
Find related entities/context
   |
Retrieve documents/data
   |
Analytics where required
   |
LLM reasoning
```

### Important principle

> **GraphRAG discovers relevant relationships and context. Analytics calculates quantitative facts.**

For example:

Question:

> How did the new promotion work?

Graph traversal might identify:

```text
Promotion
   |
   +-- Products
   +-- Customer Segments
   +-- Sites
   +-- Channels
   +-- Campaign
```

Then the analytics layer calculates:

```text
Revenue change
Transaction change
Customer acquisition
Conversion change
Margin change
Retention change
```

The LLM combines the evidence into an executive explanation.

---

# 20. RAG vs GraphRAG vs Analytics

| Requirement | Mechanism |
|---|---|
| What does the promotion policy say? | RAG |
| What documents discuss the campaign? | RAG |
| What entities are related to this promotion? | Knowledge Graph |
| Which customers bought the product? | Data Query |
| What was revenue? | Analytics |
| Why did conversion fall? | Graph + Analytics + RAG |
| What caused customer complaints? | Graph + RAG + Analytics |
| Which products contributed most? | Analytics |
| How does promotion relate to customers and products? | Graph |
| What should an executive know? | Agent + Reasoning |

---

# 21. Agentic Architecture

Once the enterprise backbone is stable, introduce the AI layer.

```text
                 CEO / CFO
                     |
                     v
             Executive Chat
                     |
                     v
          +----------------------+
          | Executive Orchestrator|
          +----------+-----------+
                     |
              Intent + Planning
                     |
          +----------+----------+
          |          |          |
          v          v          v
       GraphRAG     RAG     Analytics
          |          |          |
          v          v          v
       Graph     Documents   SQL/Python
          |          |          |
          +----------+----------+
                     |
                     v
             Evidence Layer
                     |
                     v
             Reasoning Agent
                     |
                     v
             Executive Answer
```

---

# 22. Agent Responsibilities

## Executive Orchestrator

Responsibilities:

```text
Understand question
Identify entities
Identify metrics
Identify time period
Create investigation plan
Select agents/tools
Coordinate execution
Collect evidence
Trigger validation
Generate final response
```

## Customer Intelligence Agent

```text
Retention
LTV
Segments
Frequency
Customer behavior
Churn
```

## Product Intelligence Agent

```text
Top products
Product trends
Category performance
Product affinity
Promotion/product relationship
```

## Promotion Intelligence Agent

```text
Revenue impact
Conversion
Customer acquisition
Discount impact
Margin
Retention
Segment response
```

## Digital Intelligence Agent

```text
Visits
Funnel
Conversion
Drop rates
Checkout
Website performance
```

## Voice of Customer Agent

```text
Feedback themes
Sentiment
Complaints
Product feedback
Site feedback
Emerging issues
```

## Finance Agent

```text
Revenue
Margin
Cost
Profit
Budget vs actual
Forecast
Promotion economics
```

---

# 23. Example End-to-End Flow

Question:

> **How did the new promotion work?**

## Step 1 - Intent

```text
Intent:
Promotion effectiveness
```

## Step 2 - Identify graph entities

```text
Promotion
Products
Customers
Segments
Sites
Channels
Transactions
```

## Step 3 - Graph traversal

```text
Promotion
 |
 +-- targets --> Segment
 |
 +-- promotes --> Product
 |
 +-- runs_at --> Site
 |
 +-- distributed_through --> Channel
```

## Step 4 - Retrieve analytical data

```text
Revenue
Transactions
Customers
Visits
Conversion
Margin
Retention
```

## Step 5 - Calculate

```text
Before period
During promotion
After promotion
```

Possible analytical dimensions:

```text
Customer segment
Product
Site
Region
Channel
New vs existing customer
```

## Step 6 - Retrieve supporting documents

```text
Campaign brief
Promotion strategy
Finance policy
Customer feedback
```

## Step 7 - Validate

Check:

```text
Metric definitions
Date range
Data completeness
Anomalies
Access permissions
Source consistency
```

## Step 8 - Respond

Example structure:

```text
Promotion performance

Revenue: +18%
Transactions: +21%
New customers: +12%
Conversion: +6%
Gross margin: +3%

Key insight:
Growth was strongest among new and occasional customers.
Margin improvement was smaller than revenue growth because
discounting reduced unit economics.

Evidence:
ERP/POS transactions
Customer data
Promotion definition
Campaign documents
Customer feedback
```

Numbers above are illustrative only; production answers must come from actual data.

---

# 24. Executive Experience

## CEO

Focus on:

```text
What happened?
Why?
What matters?
What changed?
What should I investigate next?
```

## CFO

Focus on:

```text
Revenue
Cost
Margin
Profit
Variance
Unit economics
Forecast
Financial impact
```

The same underlying enterprise can support different executive perspectives.

---

# 25. Evidence and Lineage

Every important answer should be traceable.

Example:

```text
Revenue
 |
 +-- defined_by --> Finance KPI Definition
 |
 +-- sourced_from --> ERP
 |
 +-- calculated_from --> Orders
 |
 +-- transformed_by --> Revenue Pipeline
 |
 +-- governed_by --> Finance Data Policy
```

The user should be able to ask:

> Where did this number come from?

The system should provide:

```text
Source
Definition
Calculation
Time period
Filters
Data freshness
Relevant query
```

---

# 26. Security and Governance

Security is cross-cutting.

Required capabilities:

```text
Authentication
Authorization
RBAC
Data-level access
PII protection
Masking
Consent
Audit logging
Tool permissions
Query permissions
Source attribution
Prompt/agent governance
Responsible AI controls
Observability
```

Important rule:

> The agent must never bypass the user's underlying data permissions.

A CEO/CFO should only retrieve information they are authorized to access.

---

# 27. Technology Direction

The project can use a hybrid stack aligned with enterprise architecture and AI development.

## Backend microservices

Recommended initial direction:

```text
.NET / ASP.NET Core
Entity Framework Core
PostgreSQL
REST APIs
OpenAPI
```

The services should stay simple.

## AI/Analytics

Use Python where it provides clear value:

```text
Python
Pandas
NumPy
statistics
ML libraries
LLM SDKs
FastAPI for AI-specific services where useful
```

## Graph

Evaluate graph technologies during Phase 3/4.

Candidate categories:

```text
Property graph
Graph database
Knowledge graph platforms
Cloud graph services
```

The technology choice should follow the required graph queries and operational constraints rather than being selected first.

## Vector/RAG

Evaluate:

```text
PostgreSQL + pgvector
Dedicated vector database
Cloud vector search
```

The initial implementation should favor simplicity.

---

# 28. Repository Structure

Suggested monorepo:

```text
enterprise-intelligence-brain/
|
+-- services/
|   |
|   +-- crm/
|   |   +-- src/
|   |   +-- tests/
|   |
|   +-- product/
|   +-- shopping/
|   +-- site/
|   +-- feedback/
|   +-- marketing/
|
+-- simulation/
|   +-- simulator/
|   +-- scenarios/
|   +-- seed-data/
|
+-- platform/
|   +-- events/
|   +-- data-platform/
|   +-- semantic-layer/
|   +-- knowledge-graph/
|   +-- rag/
|
+-- ai/
|   +-- orchestrator/
|   +-- agents/
|   +-- tools/
|   +-- analytics/
|   +-- evaluation/
|
+-- websites/
|   +-- shopping-simulator/
|   +-- content-site/
|
+-- infrastructure/
|   +-- docker/
|   +-- database/
|   +-- messaging/
|
+-- docs/
|   +-- architecture/
|   +-- adr/
|   +-- api/
|   +-- data-model/
|
+-- tests/
|   +-- integration/
|   +-- end-to-end/
|   +-- ai-evaluation/
|
+-- docker-compose.yml
+-- README.md
```

---

# 29. Development Principles

### Principle 1 - Bottom up

Do not start with the chatbot.

### Principle 2 - Real business behavior

Generate realistic relationships and events.

### Principle 3 - Service ownership

Each service owns its database.

### Principle 4 - API first

Expose simple, predictable APIs.

### Principle 5 - Event driven

Important business changes generate events.

### Principle 6 - Graph is contextual

The graph represents relationships and semantic context.

### Principle 7 - Analytics is factual

Quantitative answers come from governed analytical computation.

### Principle 8 - LLM is not the database

Never rely on LLM memory for enterprise facts.

### Principle 9 - Evidence first

Important answers should be traceable to sources.

### Principle 10 - Security by design

Authorization applies before retrieval, not after the LLM response.

---

# 30. MVP Development Roadmap

## Phase 0 - Foundation

Deliver:

```text
Repository
Docker environment
Common libraries
PostgreSQL
API conventions
OpenAPI
Logging
Configuration
```

---

## Phase 1 - CRM

Build:

```text
Customer CRUD
Profile CRUD
Segment CRUD
Database
Events
Tests
```

Acceptance:

- Customers can be created/updated/deleted.
- Profiles can be associated.
- Segments can be assigned.
- Events are published.

---

## Phase 2 - Product

Build:

```text
Product
Category
Price
Promotion
```

Acceptance:

- Products can be managed.
- Prices can change over time.
- Promotions can be created.
- Products can be associated with promotions.

---

## Phase 3 - Shopping

Build:

```text
Cart
Cart Items
Order
Order Items
Payment
```

Acceptance:

- Customer can add products.
- Cart can be abandoned.
- Order can be created.
- Order completion produces events.

---

## Phase 4 - Sites + Websites

Build:

```text
Site service
Website 1
Website 2
Visit tracking
Product view tracking
```

Acceptance:

- Simulated visits are recorded.
- Shopping journeys produce events.
- Content site produces page activity.

---

## Phase 5 - Feedback + Marketing

Build:

```text
Feedback
Campaign
Audience
Channel
```

Acceptance:

- Feedback is captured.
- Campaigns can target segments.
- Promotions can be associated with campaigns.

---

## Phase 6 - Simulation Engine

Build configurable scenarios.

Initial target:

```text
10,000+ customers
100+ products
5-10 sites
multiple promotions
hundreds of thousands of behavioral events
```

The exact scale can increase later.

Acceptance:

- Simulator can generate normal behavior.
- Simulator can create promotion uplift.
- Simulator can create website degradation.
- Simulator can create product surges.
- Simulator can create customer feedback patterns.

---

## Phase 7 - Data Platform

Build:

```text
Event ingestion
Raw data
Curated data
Analytical models
Basic KPI queries
```

Acceptance:

- Operational events are available analytically.
- Revenue can be calculated.
- Visits can be analyzed.
- Conversion can be calculated.
- Product performance can be calculated.

---

## Phase 8 - Semantic Layer

Define:

```text
Revenue
Customer
Retention
Conversion
Promotion
Product performance
Visit
Cart abandonment
```

Acceptance:

- Metrics have formal definitions.
- Metrics map to data sources.
- Query generation uses definitions.

---

## Phase 9 - Knowledge Graph

Start with:

```text
Customer
Product
Promotion
Site
Segment
Campaign
Transaction/Order
Feedback
```

Build relationships.

Acceptance:

- Graph can answer relationship queries.
- Multi-hop traversal works.
- Graph entities map to source-system IDs.
- Graph synchronization is repeatable.

---

## Phase 10 - RAG + GraphRAG

Introduce:

```text
Content ingestion
Chunking
Embeddings
Vector retrieval
Graph traversal
Hybrid retrieval
```

Acceptance:

- Document questions work.
- Entity relationship questions work.
- Multi-hop questions can retrieve relevant context.

---

## Phase 11 - Agentic Intelligence

Implement:

```text
Executive Orchestrator
Customer Agent
Product Agent
Promotion Agent
Digital Agent
Feedback Agent
Analytics Agent
```

Start with a small number of tools.

Acceptance:

- Agent identifies intent.
- Agent plans an investigation.
- Agent selects appropriate tools.
- Agent retrieves graph context.
- Agent invokes analytics.
- Agent produces evidence-backed response.

---

## Phase 12 - Executive Experience

Build:

```text
CEO/CFO chat
Conversation history
Source/evidence view
Charts
Drill-down
Follow-up questions
```

Acceptance:

The system can answer a defined set of executive scenarios end-to-end.

---

# 31. Initial Executive Question Set

Use these as evaluation scenarios:

### Promotion

```text
How did the new promotion work?
Which customer segments responded best?
Which products benefited most?
Did the promotion improve revenue?
Did it improve margin?
```

### Customer

```text
Are customer retention rates improving?
Who are our most frequent visitors?
Which customer segments are declining?
Which customers purchase most frequently?
```

### Digital

```text
Is the new website working as expected?
Where are customers dropping off?
Why did checkout conversion decline?
Which site has the highest conversion?
```

### Product

```text
What are our hot-selling products?
Which products are declining?
Which categories are growing?
Which products are frequently purchased together?
```

### Feedback

```text
What are customers complaining about?
What changed in customer sentiment?
What are the top issues with the new website?
Which products receive the most negative feedback?
```

### Finance

```text
Did sales revenue increase?
Did revenue growth translate into margin growth?
Which promotions generated the most incremental revenue?
What is driving the revenue decline?
```

---

# 32. AI Evaluation Strategy

Do not evaluate only whether the response "sounds good."

Evaluate:

```text
Intent accuracy
Entity identification
Graph retrieval accuracy
Data retrieval accuracy
Metric correctness
SQL correctness
Calculation correctness
Source attribution
Permission enforcement
Hallucination rate
Reasoning consistency
Response usefulness
```

Create known-answer scenarios using the simulation engine.

For example:

```text
Scenario:
Promotion P100 increases transactions by 20%
but reduces margin by 5%.

Expected AI discovery:
Revenue ↑
Transactions ↑
Margin ↓
```

The simulator becomes the foundation for deterministic AI evaluation.

---

# 33. Anti-Patterns to Avoid

### Avoid one giant agent

Prefer orchestrator + specialized capabilities.

### Avoid LLM direct unrestricted database access

Use governed tools.

### Avoid putting everything into the graph

High-volume facts belong in analytical stores.

### Avoid using vector search for numerical questions

Use analytics/SQL.

### Avoid using graph traversal for every question

Use the simplest retrieval mechanism that fits the question.

### Avoid hard-coded AI answers

All quantitative answers should be generated from current data.

### Avoid building a full CRM/e-commerce UI

The purpose is the data backbone.

### Avoid real enterprise integration initially

Use the synthetic enterprise first.

---

# 34. First MVP Definition

The first meaningful MVP should support:

```text
CRM
Product
Shopping
Site
Website 1
Website 2
Feedback
Marketing
Simulation
Events
Analytical Store
```

with enough data to answer:

```text
1. What are the top-selling products?
2. Which customers visit most frequently?
3. What is our conversion rate?
4. What is our cart abandonment rate?
5. How did Promotion P1 perform?
6. Which customer segment responded best?
7. Did revenue increase during the promotion?
8. Which site performed best?
9. What are customers complaining about?
10. Why did conversion change?
```

At this stage **no LLM is required**.

The goal is to prove that the synthetic enterprise generates coherent, queryable business behavior.

---

# 35. The Strategic Architecture

The eventual platform should converge toward:

```text
                        CEO / CFO
                            |
                            v
                  Executive Experience
                            |
                            v
                  Executive AI Agent
                            |
                  Intent + Planning
                            |
             +--------------+--------------+
             |              |              |
             v              v              v
          GraphRAG         RAG        Analytics Agent
             |              |              |
             v              v              v
      Knowledge Graph    Documents    SQL / Python
             |              |              |
             +--------------+--------------+
                            |
                            v
                    Evidence / Lineage
                            |
                            v
                  Enterprise Data Platform
                            |
                     Event Backbone
                            |
       +--------------------+--------------------+
       |          |          |         |         |
      CRM      Product    Shopping    Web     Feedback
       |          |          |         |         |
       +----------+----------+---------+---------+
                            |
                     Synthetic Enterprise
                            |
                    Business Simulation
```

Cross-cutting:

```text
Security
Governance
RBAC
PII
Audit
Observability
Data Quality
AI Evaluation
```

---

# 36. End State

The final experience should feel less like:

> "Ask a chatbot about our database."

and more like:

> **"Ask the enterprise brain a question and let it investigate the business."**

The core loop is:

```text
ASK
 ↓
UNDERSTAND
 ↓
PLAN
 ↓
TRAVERSE
 ↓
RETRIEVE
 ↓
ANALYZE
 ↓
CORRELATE
 ↓
VALIDATE
 ↓
EXPLAIN
 ↓
DRILL DOWN
 ↓
ACT
```

The system should progressively move from:

```text
"What happened?"
```

to:

```text
"Why did it happen?"
```

to:

```text
"What is likely to happen?"
```

to:

```text
"What options do we have?"
```

and eventually:

```text
"Execute the approved action."
```

---

# 37. Recommended First Development Step

Do **not** start GraphRAG or agent development yet.

Start with this exact sequence:

```text
1. Create repository
2. Define service boundaries
3. Define domain entities
4. Define database schemas
5. Define CRUD APIs
6. Implement CRM
7. Implement Product
8. Implement Shopping
9. Implement Site
10. Implement Websites
11. Implement Feedback
12. Implement Marketing
13. Implement Event Backbone
14. Implement Simulation Engine
15. Generate realistic data
16. Build analytical queries
17. Validate business scenarios
18. Introduce Semantic Layer
19. Introduce Knowledge Graph
20. Introduce GraphRAG
21. Introduce Agents
22. Build Executive Chat
```

This order is deliberate.

**The AI should eventually discover the enterprise rather than the developer manually feeding it artificial knowledge.**

That makes the project a realistic laboratory for enterprise agentic AI architecture.
