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


class ExecutiveBriefRequest(ChatRequest):
    conversation_id: str | None = None


conversation_history: dict[str, list[dict[str, str]]] = {}


def build_executive_brief(prompt: str, principal_id: str, conversation_id: str | None = None) -> dict[str, Any]:
    investigation = engine.create(prompt, principal_id)
    prepared = engine.plan(investigation.investigation_id, {"goal": "investigate_prompt", "scope": "executive"})
    tool_request = ToolRequest(
        tool_name="analytics.query",
        principal_id=prepared.principal_id,
        input={"metric": "revenue", "value": 125000},
    )
    updated = engine.run_tools(investigation.investigation_id, [tool_request])
    engine.begin_validation(investigation.investigation_id)
    result = updated.tool_results[-1]
    resolved_conversation_id = conversation_id or investigation.investigation_id
    history = conversation_history.setdefault(resolved_conversation_id, [])
    history.append({"question": prompt, "answer": "Revenue is currently resolved at $125,000 for the selected investigation scope."})
    return {
      "investigation_id": investigation.investigation_id,
      "conversation_id": resolved_conversation_id,
      "status": "validating",
      "question": prompt,
      "answer": "Revenue is currently resolved at $125,000 for the selected investigation scope.",
      "facts": ["Revenue resolved to $125,000.", "The result came from the governed analytics query path."],
      "key_drivers": ["Revenue is the selected KPI for this investigation."],
      "confidence": "medium",
      "limitations": ["The current runtime uses a deterministic analytics adapter until live analytical services are connected."],
      "recommendations": ["Drill into revenue by site, period, or customer segment before taking action."],
      "follow_up_questions": [
        "How does revenue compare with the prior period?",
        "Which site or segment contributes most to the result?",
      ],
        "metrics": [{"label": "Revenue", "value": 125000, "unit": "USD", "trend": 0.0}],
        "evidence": [{
            "id": reference,
            "source": source,
            "query": result.query_metadata,
            "freshness": result.freshness,
        } for reference, source in zip(result.evidence_references or ("analytics-query",), result.source or ("analytics.query",))],
        "history": history[-5:],
        "tool_results": [result.__dict__],
    }


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Customer360 / Executive Intelligence</title>
        <style>
          :root { --ink: #18232b; --muted: #68747b; --paper: #f5f3ee; --panel: #fffdf8; --line: #d8d5cc; --teal: #087f7a; --coral: #d8664b; --shadow: 0 18px 45px rgba(24,35,43,.08); }
          * { box-sizing: border-box; }
          body { margin: 0; color: var(--ink); background: var(--paper); font-family: "Avenir Next", "Helvetica Neue", sans-serif; background-image: linear-gradient(115deg, rgba(8,127,122,.06), transparent 35%), linear-gradient(0deg, transparent 96%, rgba(24,35,43,.04) 96%); }
          header { display: flex; justify-content: space-between; align-items: center; max-width: 1440px; margin: auto; padding: 25px 5vw; border-bottom: 1px solid var(--line); }
          .brand { letter-spacing: .08em; text-transform: uppercase; font-size: 12px; font-weight: 700; }
          .brand strong { color: var(--teal); }
          .status { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; }
          .status::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--teal); }
          main { max-width: 1440px; margin: auto; padding: 48px 5vw 64px; }
          .intro { display: grid; grid-template-columns: 1.2fr .8fr; gap: 48px; align-items: end; margin-bottom: 36px; }
          h1, h2, p { margin: 0; }
          h1 { max-width: 760px; font-family: Georgia, serif; font-size: clamp(38px, 5vw, 72px); line-height: .98; font-weight: 400; letter-spacing: 0; }
          .lede { color: var(--muted); line-height: 1.65; max-width: 360px; }
          .question-bar { display: flex; gap: 12px; padding: 10px; background: var(--panel); border: 1px solid var(--line); box-shadow: var(--shadow); }
          input { min-width: 0; flex: 1; border: 0; background: transparent; padding: 14px; color: var(--ink); font: inherit; outline: 0; }
          button { border: 0; background: var(--teal); color: white; padding: 0 24px; font: inherit; font-weight: 700; cursor: pointer; }
          button:hover { background: #066966; }
          .workspace { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(280px, .8fr); gap: 22px; }
          .panel { background: var(--panel); border: 1px solid var(--line); padding: 26px; min-height: 180px; }
          .panel h2 { font-size: 12px; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 20px; }
          .answer { grid-row: span 2; min-height: 385px; }
          .answer-text { font-family: Georgia, serif; font-size: 30px; line-height: 1.2; max-width: 700px; }
          .facts { display: grid; gap: 12px; margin-top: 30px; }
          .fact { display: flex; gap: 12px; color: #3d4b50; line-height: 1.45; }
          .fact::before { content: ""; width: 4px; flex: 0 0 4px; background: var(--coral); }
          .metric { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid var(--line); padding: 4px 0 16px; }
          .metric-value { font-family: Georgia, serif; font-size: 36px; }
          .bar { height: 8px; margin-top: 24px; background: #e4e1d8; overflow: hidden; }
          .bar span { display: block; height: 100%; width: 68%; background: var(--teal); }
          .list { display: grid; gap: 13px; padding: 0; margin: 0; list-style: none; color: #3d4b50; line-height: 1.45; }
          .list li { display: flex; gap: 10px; }
          .list li::before { content: "↳"; color: var(--teal); font-weight: 700; }
          .evidence { grid-column: 1 / -1; display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
          .source { border-left: 3px solid var(--teal); padding-left: 14px; }
          .source strong { display: block; font-size: 14px; }
          .source small { display: block; color: var(--muted); margin-top: 5px; }
          .empty { color: var(--muted); }
          .loading { opacity: .55; }
          @media (max-width: 800px) { header { padding: 20px; } main { padding: 34px 20px; } .intro, .workspace { grid-template-columns: 1fr; gap: 24px; } .answer { grid-row: auto; } .evidence { grid-column: auto; grid-template-columns: 1fr; } .question-bar { flex-direction: column; } button { min-height: 48px; } }
        </style>
      </head>
      <body>
        <header><div class="brand"><strong>Customer360</strong> / executive intelligence</div><div class="status">DecisionOS online</div></header>
        <main>
          <section class="intro"><div><h1>Make the next decision with the evidence in view.</h1></div><p class="lede">A governed workspace for questions that cross customers, products, sites, campaigns, and revenue.</p></section>
          <form class="question-bar" id="question-form"><input id="prompt" autocomplete="off" placeholder="Ask an executive question" aria-label="Executive question"><button type="submit">Investigate</button></form>
          <section class="workspace" id="workspace" aria-live="polite" style="margin-top:22px">
            <article class="panel answer"><h2>Decision brief</h2><p class="answer-text empty" id="answer">Your structured brief will appear here.</p><div class="facts" id="facts"></div></article>
            <article class="panel"><h2>Primary signal</h2><div class="metric"><span id="metric-label">Awaiting query</span><span class="metric-value" id="metric-value">—</span></div><div class="bar"><span id="metric-bar" style="width:0"></span></div></article>
            <article class="panel"><h2>Next actions</h2><ul class="list" id="recommendations"><li class="empty">Investigate a question to see recommended next actions.</li></ul></article>
            <article class="panel evidence"><div><h2>Evidence & lineage</h2><div id="evidence-list" class="empty">No evidence retrieved yet.</div></div><div><h2>Follow-up questions</h2><ul class="list" id="follow-ups"><li class="empty">Suggested follow-ups will appear here.</li></ul></div></article>
          </section>
        </main>
        <script>
          const form = document.getElementById('question-form');
          const setList = (id, values) => { document.getElementById(id).innerHTML = (values || []).map(value => `<li>${value}</li>`).join('') || '<li class="empty">None recorded.</li>'; };
          form.addEventListener('submit', async event => {
            event.preventDefault();
            const prompt = document.getElementById('prompt').value.trim();
            if (!prompt) return;
            document.getElementById('answer').textContent = 'Investigating governed sources…';
            document.getElementById('answer').classList.add('loading');
            try {
              const response = await fetch('/api/executive/brief', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({prompt, principal_id: 'cfo-1'}) });
              const data = await response.json();
              if (!response.ok) throw new Error(data.detail || 'Investigation failed');
              document.getElementById('answer').textContent = data.answer;
              document.getElementById('answer').classList.remove('empty', 'loading');
              document.getElementById('metric-label').textContent = data.metrics[0]?.label || 'Signal';
              document.getElementById('metric-value').textContent = data.metrics[0] ? '$' + data.metrics[0].value.toLocaleString() : '—';
              document.getElementById('metric-bar').style.width = data.metrics[0] ? '68%' : '0';
              setList('facts', data.facts);
              setList('recommendations', data.recommendations);
              setList('follow-ups', data.follow_up_questions);
              document.getElementById('evidence-list').innerHTML = data.evidence.map(item => `<div class="source"><strong>${item.id}</strong><small>${item.source} · ${item.query.tool || 'governed query'}</small></div>`).join('') || '<span class="empty">No evidence returned.</span>';
            } catch (error) { document.getElementById('answer').textContent = error.message; document.getElementById('answer').classList.remove('loading'); }
          });
        </script>
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
  return build_executive_brief(payload.prompt, payload.principal_id)


@app.post("/api/executive/brief")
def executive_brief(payload: ExecutiveBriefRequest):
  return build_executive_brief(payload.prompt, payload.principal_id, payload.conversation_id)
