# Customer360 One-Page System Architecture

Compact view for a single PPT slide or architecture image.

```mermaid
flowchart LR
    subgraph L1[Experience]
        UI[Executive UI<br/>questions and decision briefs]
    end

    subgraph L2[Agentic Layer]
        API[Agent API]
        DOS[DecisionOS<br/>orchestrator, domain agents,<br/>permissions, evidence, audit]
        TOOLS[Governed tools<br/>analytics, graph, RAG, scenarios]
        API --> DOS --> TOOLS
    end

    subgraph L3[SQL / Query Layer]
        PARSER[Question to SQL<br/>schema context, parser,<br/>read-only validator]
    end

    subgraph L4[Data Platform]
        DP[Ingestion and semantic layer]
        STORE[Warehouse, graph, RAG<br/>quality and lineage]
        DP --> STORE
    end

    subgraph L5[Enterprise Layer]
        SERVICES[CRM, Product, Shopping, Site<br/>Feedback, Marketing, Orchestration]
        DBS[(One private DB per service<br/>no shared operational tables)]
        EVENTS[Event service<br/>immutable domain events]
        SERVICES --> DBS
        SERVICES --> EVENTS
    end

    UI -->|business question| API
    TOOLS -->|governed analytics request| PARSER
    PARSER -->|authorized read-only query| DP
    EVENTS -->|ingest and replay| DP
    DP -.->|controlled APIs and backfill| SERVICES
    STORE -->|facts, lineage, evidence| DOS
    DOS -->|validated executive brief| API

    classDef experience fill:#e8f0ff,stroke:#3973c6,color:#16345f
    classDef agentic fill:#e5f5ed,stroke:#2d8a62,color:#164a35
    classDef query fill:#fcebdc,stroke:#c66b2d,color:#5d2f16
    classDef data fill:#fff3d6,stroke:#bd8422,color:#5c4213
    classDef enterprise fill:#f0edf8,stroke:#7664a8,color:#352d55
    class UI experience
    class API,DOS,TOOLS agentic
    class PARSER query
    class DP,STORE data
    class SERVICES,DBS,EVENTS enterprise
```

## Core architecture rules

- **Enterprise:** Each microservice owns its API, domain logic, schema, and private database.
- **Events:** Services publish immutable domain events; the Data Platform ingests and replays them.
- **Data Platform:** Owns cross-service joins, curated models, metrics, semantic definitions, lineage, graph, RAG, and quality checks.
- **SQL boundary:** Questions become authorized schema context and validated read-only SQL. The parser cannot write to operational stores.
- **Agentic layer:** DecisionOS plans investigations and calls governed tools. Agents never access service databases directly.
- **Evidence:** Answers return facts with source, freshness, definitions, limitations, and audit references.

## Slide takeaway

`Private service databases -> domain events and APIs -> Data Platform -> governed SQL and tools -> DecisionOS -> evidence-backed executive brief`
