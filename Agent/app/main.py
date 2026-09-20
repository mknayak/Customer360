from __future__ import annotations

from typing import Any, Mapping

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from Agent.DecisionOS.runtime.decision_os.adapters import ServiceAdapters
from Agent.DecisionOS.runtime.decision_os.engine import InvestigationEngine
from Agent.DecisionOS.runtime.decision_os.models import PermissionDecision, ToolRequest
from Agent.DecisionOS.runtime.decision_os.persistence import InMemoryPersistence
from Agent.DecisionOS.runtime.decision_os.catalog import register_tool_catalog
from Agent.DecisionOS.runtime.decision_os.tools import ToolDispatcher


def allow_all(principal_id: str, resource: str) -> PermissionDecision:
    return PermissionDecision(True, principal_id, resource, "allowed")


def analytics_metric_handler(inputs: Mapping[str, Any]):
    metric = inputs.get("metric", "revenue")
    value = inputs.get("value", 0)
    return {"metric": metric, "value": value, "status": "resolved"}


def entity_mapping_handler(inputs: Mapping[str, Any]):
    return service_adapters.entity_mapping(inputs["entity_type"], inputs["entity_id"])


def customer_snapshot_handler(inputs: Mapping[str, Any]):
  return service_adapters.customer_snapshot(inputs["customer_id"])


def build_dispatcher() -> ToolDispatcher:
    dispatcher = ToolDispatcher(allow_all)
    register_tool_catalog(
        dispatcher,
        {
          "customer.snapshot": customer_snapshot_handler,
            "analytics.query": analytics_metric_handler,
            "semantic.entity_mapping": entity_mapping_handler,
        },
    )
    return dispatcher


app = FastAPI(title="Customer360 Agent App", version="0.1.0")
service_adapters = ServiceAdapters.from_origins(
    {
        "crm": "http://127.0.0.1:8001",
        "product": "http://127.0.0.1:8002",
        "shopping": "http://127.0.0.1:8003",
        "site": "http://127.0.0.1:8004",
        "feedback": "http://127.0.0.1:8005",
        "marketing": "http://127.0.0.1:8006",
        "events": "http://127.0.0.1:8007",
        "orchestration": "http://127.0.0.1:8008",
    }
)
engine = InvestigationEngine(InMemoryPersistence(), build_dispatcher())


class InvestigationCreateRequest(BaseModel):
    question: str = Field(..., min_length=3)
    principal_id: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    principal_id: str = Field(default="cfo-1", min_length=1)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
    <html>
      <head>
        <title>Customer360 Agent</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 40px; background: #0f172a; color: #e2e8f0; }
          .card { max-width: 700px; margin: 0 auto; background: #111827; padding: 24px; border-radius: 12px; }
          textarea, button { width: 100%; margin-top: 12px; padding: 12px; border-radius: 8px; }
          button { background: #2563eb; color: white; border: none; cursor: pointer; }
          pre { white-space: pre-wrap; background: #020617; padding: 12px; border-radius: 8px; }
        </style>
      </head>
      <body>
        <div class="card">
          <h1>Customer360 Agent</h1>
          <p>Ask a prompt to start an investigation.</p>
          <textarea id="prompt" rows="6" placeholder="Example: Why did revenue fall last week?"></textarea>
          <button onclick="sendPrompt()">Ask Agent</button>
          <pre id="result">Waiting for prompt...</pre>
          <script>
            async function sendPrompt() {
              const prompt = document.getElementById('prompt').value;
              const resultBox = document.getElementById('result');
              try {
                const response = await fetch('/api/agent/chat', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ prompt, principal_id: 'cfo-1' })
                });
                const data = await response.json();
                resultBox.textContent = JSON.stringify(data, null, 2);
              } catch (error) {
                resultBox.textContent = 'Request failed: ' + error;
              }
            }
          </script>
        </div>
      </body>
    </html>
    """


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agent-app"}


@app.get("/api/adapters/health")
def adapter_health():
  return service_adapters.health()


@app.post("/api/investigations")
def create_investigation(payload: InvestigationCreateRequest):
    investigation = engine.create(payload.question, payload.principal_id)
    return {
        "investigation_id": investigation.investigation_id,
        "status": investigation.status,
        "question": investigation.question,
    }


@app.post("/api/investigations/{investigation_id}/run")
def run_investigation(investigation_id: str):
    try:
        prepared = engine.plan(investigation_id, {"goal": "analyze_kpi", "metric": "revenue"})
        tool_request = ToolRequest(
            tool_name="analytics.query",
            principal_id=prepared.principal_id,
            input={"metric": "revenue", "value": 125000},
        )
        updated = engine.run_tools(investigation_id, [tool_request])
        engine.begin_validation(investigation_id)
        return {
            "investigation_id": investigation_id,
            "status": updated.status.value,
            "tool_results": [result.__dict__ for result in updated.tool_results],
        }
    except Exception as exc:  # pragma: no cover - intentionally narrow for app ergonomics
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/agent/chat")
def chat(payload: ChatRequest):
    investigation = engine.create(payload.prompt, payload.principal_id)
    prepared = engine.plan(investigation.investigation_id, {"goal": "investigate_prompt"})
    tool_request = ToolRequest(
        tool_name="analytics.query",
        principal_id=prepared.principal_id,
        input={"metric": "revenue", "value": 125000},
    )
    updated = engine.run_tools(investigation.investigation_id, [tool_request])
    engine.begin_validation(investigation.investigation_id)
    return {
        "investigation_id": investigation.investigation_id,
        "status": updated.status.value,
        "answer": f"I investigated: '{payload.prompt}'. The current KPI signal resolved to revenue = 125000.",
        "tool_results": [result.__dict__ for result in updated.tool_results],
    }
