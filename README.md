# Customer360 Enterprise Intelligence Brain

Customer360 is a synthetic enterprise platform for exploring customer and business operations, producing event-driven analytical data, and answering executive questions through governed tools. The repository combines operational APIs, a browser-based simulator, an analytical data platform, and the DecisionOS agent runtime.

The system is developed bottom-up: synthetic services and events first, then analytics and semantic definitions, followed by governed investigation and decision experiences. Most generated data is synthetic. The LLM is an optional investigator and wording assistant; it is not the system of record.

See [overview.md](overview.md) for user-facing capabilities and workflows, and [architecture.md](architecture.md) for component boundaries, data flows, and implementation status.

## Repository Map

- `Enterprise/Services/`: CRM, Product, Shopping, Site, Feedback, Marketing, Events, and Orchestration APIs. Each service owns its SQLite database.
- `Enterprise/Simulator/`: browser simulator, static customer/content experiences, event-generating scenarios, and a same-origin API proxy.
- `Enterprise/DataPlatform/`: event ingestion, SQLite warehouse, curated KPIs, semantic query execution, quality checks, and governed read-only Text-to-SQL APIs.
- `Agent/app/`: FastAPI application and executive-facing browser interface.
- `Agent/DecisionOS/`: agent/tool contracts, prompts, skills, governance policies, and executable runtime.
- `docs/`: architecture and question-to-answer design notes.
- `logs/`: local model request logs; generated logs are not source data.

## Requirements

- Python 3.11 or newer.
- Bash on macOS/Linux to run the complete local stack with `run.sh`.
- PowerShell on Windows to run the complete local stack with `run.ps1`.

The application uses SQLite and does not require a separate database server. A compatible OpenAI-style endpoint is optional; without one the agent app uses its deterministic local provider.

## Set Up

Run these commands from the repository root. The repository uses one shared virtual environment for all services.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "pytest>=8" httpx2
```

Copy `.env.example` to `.env` to customize local hosts, ports, model configuration, and database paths. The default configuration is suitable for a local run. Keep API keys in `.env`; do not commit them.

## Run the Application

On macOS/Linux, start the complete locally wired stack from the repository root:

```bash
./run.sh
```

The launcher reads `.env` when present and starts available services on `127.0.0.1`. Press `Ctrl+C` to stop the processes it started. The script force-stops any process already listening on one of its configured ports before starting, so review port ownership first if you have other local services running.

On Windows, run the equivalent PowerShell launcher from the repository root:

```powershell
.\run.ps1
```

It starts the same services and UI, loads simple `KEY=value` assignments from `.env` when present, and stops the processes it started when interrupted. It also force-stops processes already listening on configured ports before launch.

Open the main experiences:

- Simulator: [http://127.0.0.1:8080](http://127.0.0.1:8080)
- Content site: [http://127.0.0.1:8080/content.html](http://127.0.0.1:8080/content.html)
- Agent and executive decision UI: [http://127.0.0.1:8009](http://127.0.0.1:8009)
- Agent API docs: [http://127.0.0.1:8009/docs](http://127.0.0.1:8009/docs)
- Data Platform API docs: [http://127.0.0.1:8010/docs](http://127.0.0.1:8010/docs)

The simulator proxies browser API requests to the local services. To get populated analytics, create or simulate service activity, then allow the Agent or Data Platform to ingest events. Data Platform ingestion is also triggered by analytics requests made through the agent.

### Service Ports

| Component | Default port | Health endpoint |
|---|---:|---|
| CRM | 8001 | `/api/health` |
| Product | 8002 | `/api/health` |
| Shopping | 8003 | `/api/health` |
| Site | 8004 | `/api/health` |
| Feedback | 8005 | `/api/health` |
| Marketing | 8006 | `/api/health` |
| Events | 8007 | `/api/health` |
| Orchestration | 8008 | `/api/health` |
| Agent application | 8009 | `/api/health` |
| Data Platform | 8010 | `/api/health` |
| Simulator and API proxy | 8080 | Browser UI |

Override ports using the corresponding variables in `.env.example`. `run.sh` also supports `SERVICE_HOST` and `PYTHON`.

## Useful Workflows

Generate a deterministic scenario dataset without starting the stack:

```bash
.venv/bin/python Enterprise/Simulator/scenario_engine.py \
  --output /tmp/customer360-scenario.json \
  --scenario promotion_uplift \
  --seed 42
```

Scenario modes include `normal`, `promotion_uplift`, `website_degradation`, `product_surge`, and `feedback_spike`. The simulator also provides anonymous browsing, cart abandonment, successful checkout, and failed payment journeys.

Ask a question from the executive UI or call `POST /api/executive/brief` on the Agent API. The response carries investigation information, metric results, sources, query metadata, freshness, limitations, and other evidence fields. Optional model settings live in `.env.example`; leave `LLM_BASE_URL` and `LLM_API_KEY` blank to use the deterministic provider.

## Tests

Run the Data Platform, DecisionOS runtime, and Agent app test suites from the repository root:

```bash
PYTHONPATH=Enterprise/DataPlatform .venv/bin/python -m pytest -q \
  Enterprise/DataPlatform/tests Agent/DecisionOS/runtime/tests Agent/app/tests
```

Service test suites can be run from an individual service directory, for example `Enterprise/Services/crm`, with `.venv/bin/python -m pytest tests`. The DecisionOS runtime tests can also be run from `Agent/DecisionOS/runtime` with `python -m pytest` after activating the shared environment.

## Data and Local State

Operational services, the Event service, and the Data Platform persist local SQLite files under their respective `data/` directories. These are development stores, not a shared operational database. The Agent app currently constructs its runtime state in-process; in-memory conversations and runtime stores do not survive a process restart. Generated database files and logs should be treated as local application state.

For detailed subsystem contracts and service-specific endpoints, see the README files under `Enterprise/Services/`, `Enterprise/DataPlatform/`, `Enterprise/Simulator/`, and `Agent/`.

## Implementation Status

This is an evolving local development system, not a production deployment. The operational APIs, event envelopes and local event store, simulator, warehouse/KPI paths, semantic query compiler, read-only SQL controls, and initial DecisionOS runtime are implemented. Some target architecture capabilities remain in-memory or are specified ahead of their production integration. In particular, the agent's graph and RAG stores are local runtime components, while event-backed graph/RAG projections, durable agent persistence, production identity and authorization, and a broker-backed event bus are not implied by this local setup.