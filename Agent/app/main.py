from __future__ import annotations

import json
import os
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
from pathlib import Path
from typing import Any, Literal, Mapping

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from Agent.DecisionOS.runtime.decision_os.adapters import ServiceAdapters
from Agent.DecisionOS.runtime.decision_os.agents import AgentFinding, AgentPack
from Agent.DecisionOS.runtime.decision_os.engine import InvestigationEngine
from Agent.DecisionOS.runtime.decision_os.evidence import EvidencePipeline
from Agent.DecisionOS.runtime.decision_os.models import DecisionBrief, PermissionDecision, ToolRequest
from Agent.DecisionOS.runtime.decision_os.persistence import InMemoryPersistence
from Agent.DecisionOS.runtime.decision_os.catalog import register_tool_catalog
from Agent.DecisionOS.runtime.decision_os.graph import GraphStore, graph_tool_handlers
from Agent.DecisionOS.runtime.decision_os.rag import Document, DocumentStore, GraphRAGRetriever, rag_tool_handlers
from Agent.DecisionOS.runtime.decision_os.semantic import SemanticRegistry
from Agent.DecisionOS.runtime.decision_os.model_provider import DeterministicModelProvider, OpenAICompatibleModelProvider, ModelRequest
from Agent.DecisionOS.runtime.decision_os.tools import PermissionMap, ToolExecution, ToolDispatcher


def allow_all(principal_id: str, resource: str) -> PermissionDecision:
    return PermissionDecision(True, principal_id, resource, "allowed")


PERMISSIONS = PermissionMap(
    {
        "cfo-1": {"analytics", "semantic", "graph", "rag", "governance", "customer", "product", "order", "visit", "campaign", "feedback"},
        "executive-1": {"analytics", "semantic", "graph", "rag", "governance"},
    }
)


def analytics_metric_handler(inputs: Mapping[str, Any]):
    metric = inputs.get("metric", "revenue")
    fallback = inputs.get("value", 0)
    origin = os.getenv("DATA_PLATFORM_ORIGIN", "http://127.0.0.1:8010")
    try:
        ingest_request = Request(f"{origin.rstrip('/')}/api/ingest/event-service", data=b"", method="POST")
        with urlopen(ingest_request, timeout=5):
            pass
        with urlopen(f"{origin.rstrip('/')}/api/kpis/{metric}", timeout=5) as response:
            result = json.loads(response.read())
        return ToolExecution(
            data={**result, "status": "resolved"},
            source=(f"data-platform:/api/kpis/{metric}",),
            query_metadata={"tool": "analytics.query", "metric": metric, "live": True},
            freshness={"retrieved_at": "live"},
            evidence_references=(f"analytics:{metric}",),
        )
    except (URLError, OSError, json.JSONDecodeError):
        return ToolExecution(
            data={"metric": metric, "value": fallback, "status": "fallback"},
            source=("analytics.query",),
            query_metadata={"tool": "analytics.query", "metric": metric, "live": False},
            warnings=("Live Data Platform unavailable; deterministic fallback used",),
            evidence_references=(f"analytics-fallback:{metric}",),
        )


def resolve_metric(prompt: str) -> tuple[str, str, str]:
    """Map question language to an approved Data Platform KPI."""
    normalized = prompt.casefold()
    if ("segment" in normalized or "segments" in normalized) and any(
        keyword in normalized for keyword in ("convert", "conversion", "customer")
    ):
        return "segment_conversion", "Segment conversion", "results"
    candidates = (
        ("page_popularity", "Most visited page", "pages"),
        ("page_dropoff", "Most dropped page", "pages"),
        ("product_performance", "Product performance", "results"),
        ("cart_abandonment", "Cart abandonment", "%"),
        ("conversion", "Conversion rate", "%"),
        ("visits", "Visits", "visits"),
        ("retention", "Customer retention", "%"),
        ("revenue", "Revenue", "USD"),
    )
    keywords = {
        "page_popularity": ("most visited page", "popular page", "top page", "most viewed page", "page popularity"),
        "page_dropoff": ("dropped page", "drop off", "dropoff", "page exit", "exited page", "bounce page"),
        "product_performance": ("product", "sku", "units", "sell-through", "underperform"),
        "cart_abandonment": ("abandon", "cart"),
        "conversion": ("conversion", "funnel"),
        "visits": ("visit", "traffic", "session"),
        "retention": ("retention", "churn", "repeat customer", "repeat purchase"),
        "revenue": ("revenue", "sales", "margin", "profit", "kpi"),
    }
    for metric, label, unit in candidates:
        if any(keyword in normalized for keyword in keywords[metric]):
            return metric, label, unit
    return "revenue", "Revenue", "USD"


def format_metric_answer(metric: str, label: str, value: Any, unit: str) -> tuple[str, list[str], list[str]]:
    if metric == "segment_conversion":
        if not value:
            return (
                "Segment conversion cannot be calculated because no customer segment assignments are available.",
                ["CRM currently contains no segment memberships for customers."],
                ["Which customer segments should be assigned first?", "Would you like to load the segment assignments before calculating conversion?"],
            )
        return (
            f"Segment conversion returned {len(value)} segments.",
            [f"{row['segment']}: {row['conversion_rate']:.2%} conversion" for row in value[:5]],
            ["Which segment should be investigated next?"],
        )
    if metric == "product_performance":
        rows = value if isinstance(value, list) else []
        top = rows[0] if rows else None
        def product_name(row: Mapping[str, Any]) -> str:
            product_id = str(row["product_id"])
            try:
                product = service_adapters.product.get(product_id)
                attributes = product.data.get("attributes", {})
                return attributes.get("name") or attributes.get("sku") or product_id
            except Exception:
                return product_id

        top_name = product_name(top) if top else ""
        answer = f"Top-selling product by units is {top_name} with {rows[0]['units']} units." if rows else "No product performance records are available after refreshing order history."
        facts = [f"{product_name(row)}: {row['units']} units and {row['revenue']:.2f} revenue" for row in rows[:3]]
        follow_ups = ["Which products are underperforming relative to forecast?", "Which category contributes most revenue?"]
        return answer, facts, follow_ups
    if metric == "page_dropoff":
        rows = value if isinstance(value, list) else []
        if not rows:
            return (
                "No page-dropoff events are available yet.",
                ["The analytics store has no recorded content Exit events."],
                ["Run the user-visit simulation to generate page activity."],
            )
        top = rows[0]
        answer = f"The most dropped page is {top['page']} with {top['exits']} exits."
        facts = [f"{row['page']}: {row['exits']} exits" for row in rows[:5]]
        return answer, facts, ["What content or device segment has the highest dropoff?", "What was the average time on the dropped page?"]
    if metric == "page_popularity":
        rows = value if isinstance(value, list) else []
        if not rows:
            return (
                "No page-level content views are available yet.",
                ["The analytics store has no recorded ContentView events."],
                ["Run the user-visit simulation to generate page activity."],
            )
        top = rows[0]
        answer = f"The most visited page is {top['page']} with {top['views']} views."
        facts = [f"{row['page']}: {row['views']} views" for row in rows[:5]]
        return answer, facts, ["Which audience segment visits this page most?", "What is the dropoff rate from this page?"]
    numeric = float(value or 0)
    display_value = numeric * 100 if unit == "%" else numeric
    formatted = f"{display_value:,.2f}" if unit in {"USD", "%"} else f"{display_value:,.0f}"
    suffix = "%" if unit == "%" else f" {unit}" if unit else ""
    answer = f"{label} is currently {formatted}{suffix}."
    facts = [f"{label} resolved to {formatted}{suffix}."]
    follow_ups = {
        "revenue": ["Which site or segment contributes most to revenue?", "How does revenue compare with the prior period?"],
        "visits": ["Which site or channel contributes most visits?", "How does traffic convert to orders?"],
        "conversion": ["Which funnel step has the largest drop-off?", "How does conversion vary by site?"],
        "cart_abandonment": ["Which site or channel has the highest abandonment?", "What products are most common in abandoned carts?"],
        "retention": ["Which customer segment has the strongest retention?", "How does retention vary by period?"],
    }.get(metric, ["Which segment should be investigated next?"])
    return answer, facts, follow_ups
def entity_mapping_handler(inputs: Mapping[str, Any]):
    return service_adapters.entity_mapping(inputs["entity_type"], inputs["entity_id"])


def customer_snapshot_handler(inputs: Mapping[str, Any]):
  return service_adapters.customer_snapshot(inputs["customer_id"])


def build_dispatcher() -> ToolDispatcher:
    dispatcher = ToolDispatcher(PERMISSIONS)
    register_tool_catalog(
        dispatcher,
        {
          "customer.snapshot": customer_snapshot_handler,
            "analytics.query": analytics_metric_handler,
            "semantic.lookup": semantic_registry.lookup_execution,
            "semantic.entity_mapping": entity_mapping_handler,
            **graph_tool_handlers(graph_store),
            **rag_tool_handlers(rag_retriever),
        },
    )
    return dispatcher


app = FastAPI(title="Customer360 Agent App", version="0.1.0")
service_adapters = ServiceAdapters.from_origins(
    {
        "crm": os.getenv("CRM_ORIGIN", "http://127.0.0.1:8001"),
        "product": os.getenv("PRODUCT_ORIGIN", "http://127.0.0.1:8002"),
        "shopping": os.getenv("SHOPPING_ORIGIN", "http://127.0.0.1:8003"),
        "site": os.getenv("SITE_ORIGIN", "http://127.0.0.1:8004"),
        "feedback": os.getenv("FEEDBACK_ORIGIN", "http://127.0.0.1:8005"),
        "marketing": os.getenv("MARKETING_ORIGIN", "http://127.0.0.1:8006"),
        "events": os.getenv("EVENTS_ORIGIN", "http://127.0.0.1:8007"),
        "orchestration": os.getenv("ORCHESTRATION_ORIGIN", "http://127.0.0.1:8008"),
    }
)
semantic_registry = SemanticRegistry()
graph_store = GraphStore()
document_store = DocumentStore()
rag_retriever = GraphRAGRetriever(document_store, graph_store)
model_provider = OpenAICompatibleModelProvider.from_environment() or DeterministicModelProvider()
engine = InvestigationEngine(InMemoryPersistence(), build_dispatcher())
agent_pack = AgentPack()
evidence_pipeline = EvidencePipeline()


class InvestigationCreateRequest(BaseModel):
    question: str = Field(..., min_length=3)
    principal_id: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    principal_id: str = Field(default="cfo-1", min_length=1)


class ExecutiveBriefRequest(ChatRequest):
    conversation_id: str | None = None
    executive_role: Literal["CEO", "CFO"] = "CFO"


class InvestigationRequest(ChatRequest):
    time_period: str | None = None


conversation_history: dict[str, list[dict[str, str]]] = {}
TEMPLATE_PATH = Path(__file__).parent / "templates" / "index.html"


def build_executive_brief(
    prompt: str,
    principal_id: str,
    conversation_id: str | None = None,
    executive_role: str = "CFO",
) -> dict[str, Any]:
    started_at = time.perf_counter()
    steps: list[dict[str, Any]] = []

    def add_step(title: str, detail: str, meta: Mapping[str, Any] | None = None) -> None:
        steps.append(
            {
                "title": title,
                "detail": detail,
                "meta": dict(meta or {}),
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1),
            }
        )

    permission = PERMISSIONS(principal_id, "analytics")
    add_step(
        "Checked authorization",
        f"Verified principal '{principal_id}' is permitted to access the analytics domain before touching any tool.",
        {"principal_id": principal_id, "allowed": permission.allowed, "reason": permission.reason},
    )
    if not permission.allowed:
        raise HTTPException(status_code=403, detail=permission.reason)

    metric, metric_label, metric_unit = resolve_metric(prompt)
    add_step(
        "Understood the question",
        f"Read \"{prompt}\" and mapped the language to the governed metric '{metric_label}'.",
        {"metric": metric, "executive_role": executive_role},
    )

    investigation = engine.create(prompt, principal_id)
    add_step(
        "Opened an investigation",
        "Created a tracked investigation record so every later step stays auditable.",
        {"investigation_id": investigation.investigation_id, "status": str(investigation.status)},
    )

    prepared = engine.plan(investigation.investigation_id, {"goal": "investigate_prompt", "scope": "executive"})
    add_step(
        "Planned the approach",
        "Chose the analytics tool path as the fastest route to a governed, evidence-backed answer.",
        {"plan": dict(prepared.plan), "status": str(prepared.status)},
    )

    tool_request = ToolRequest(
        tool_name="analytics.query",
        principal_id=prepared.principal_id,
        input={"metric": metric},
    )
    add_step(
        "Chose a tool to query",
        f"Decided to call '{tool_request.tool_name}' with metric='{metric}' instead of guessing an answer.",
        {"tool": tool_request.tool_name, "input": dict(tool_request.input)},
    )

    updated = engine.run_tools(investigation.investigation_id, [tool_request])
    result = updated.tool_results[-1]
    live = result.query_metadata.get("live") is True
    add_step(
        "Queried the system",
        f"Executed '{tool_request.tool_name}' against {'the live Data Platform' if live else 'a deterministic fallback dataset (live platform unreachable)'}.",
        {"source": list(result.source), "live": live, "warnings": list(result.warnings)},
    )

    engine.begin_validation(investigation.investigation_id)
    add_step(
        "Validated the result",
        "Moved the investigation into validation so the raw tool output is checked before it becomes an answer.",
        {"status": "validating"},
    )

    value = result.data.get("value", 0) if isinstance(result.data, Mapping) else 0
    answer, facts, follow_up_questions = format_metric_answer(metric, metric_label, value, metric_unit)
    add_step(
        "Analyzed the data",
        f"Interpreted the returned value for '{metric_label}' and drafted facts, hypotheses, and next actions.",
        {"facts_extracted": len(facts)},
    )

    model_used = "deterministic"
    if isinstance(model_provider, OpenAICompatibleModelProvider):
        try:
            model_response = model_provider.complete(ModelRequest(prompt, tuple(facts), ("semantic.lookup", "analytics.query", "rag.search", "graph.search")))
            answer = model_response.text
            model_used = model_response.model
            add_step(
                "Synthesized with the LLM",
                f"Asked '{model_used}' to phrase the governed facts into an executive answer.",
                {"model": model_used},
            )
        except Exception as error:
            facts.append("Configured LLM synthesis failed; the governed deterministic answer was retained.")
            follow_up_questions.append(f"LLM synthesis unavailable: {error}")
            add_step(
                "LLM synthesis failed",
                "Fell back to the governed deterministic answer template.",
                {"error": str(error)},
            )
    else:
        add_step(
            "Synthesized the answer",
            "Used the deterministic governed template because no LLM provider is configured.",
            {"model": model_used},
        )

    source_label = result.source[0] if result.source else "analytics.query"
    resolved_conversation_id = conversation_id or investigation.investigation_id
    history = conversation_history.setdefault(resolved_conversation_id, [])
    history.append({"question": prompt, "answer": answer})
    add_step(
        "Recorded evidence",
        f"Attached {len(result.evidence_references or ())} evidence reference(s) so the answer stays traceable to source.",
        {"evidence_references": list(result.evidence_references or ())},
    )
    return {
      "investigation_id": investigation.investigation_id,
      "conversation_id": resolved_conversation_id,
    "executive_role": executive_role,
    "model": model_used,
      "status": "validating",
      "question": prompt,
        "answer": answer,
        "facts": facts + ["The result came from the governed analytics query path."],
            "key_drivers": [f"{metric_label} was selected from the question language."],
      "confidence": "medium",
    "limitations": [] if live else ["Live Data Platform unavailable; deterministic analytics fallback was used."],
      "recommendations": ["Drill into revenue by site, period, or customer segment before taking action."],
            "follow_up_questions": follow_up_questions,
                "metrics": [{"label": metric_label, "value": value, "unit": metric_unit, "trend": 0.0}],
        "evidence": [{
            "id": reference,
            "source": source,
            "query": result.query_metadata,
            "freshness": result.freshness,
        } for reference, source in zip(result.evidence_references or ("analytics-query",), result.source or ("analytics.query",))],
        "history": history[-5:],
        "tool_results": [result.__dict__],
        "thinking_steps": steps,
    }


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agent-app"}


@app.get("/api/adapters/health")
def adapter_health():
  return service_adapters.health()


@app.get("/api/agent/model-status")
def model_status() -> dict[str, str | bool]:
        return {"configured": isinstance(model_provider, OpenAICompatibleModelProvider), "provider": getattr(model_provider, "model", "deterministic-test")}


@app.post("/api/semantic/lookup")
def semantic_lookup(payload: dict[str, Any]) -> dict[str, Any]:
    return semantic_registry.lookup_execution(payload).__dict__


@app.post("/api/graph/sync")
def sync_graph(payload: dict[str, Any]) -> dict[str, Any]:
    version = graph_store.sync(payload.get("entities", ()), payload.get("relationships", ()))
    return {"status": "synced", "graph_version": version}


@app.get("/api/graph/paths")
def graph_paths(from_id: str, to_id: str, max_depth: int = 6) -> dict[str, Any]:
    return graph_store.paths(from_id, to_id, max_depth).__dict__


@app.get("/api/graph/neighbors")
def graph_neighbors(entity_type: str, entity_id: str, max_results: int = 100) -> dict[str, Any]:
    return graph_store.neighbors(entity_type, entity_id, max_results=max_results).__dict__


@app.post("/api/graph/search")
def graph_search(payload: dict[str, Any]) -> dict[str, Any]:
    return graph_store.search(payload["query"], payload.get("max_results", 25)).__dict__


@app.post("/api/rag/documents")
def ingest_document(payload: dict[str, Any]) -> dict[str, Any]:
    document = Document(
        document_id=payload["document_id"],
        title=payload["title"],
        content=payload["content"],
        source=payload["source"],
        version=payload.get("version", "1"),
        document_type=payload.get("document_type", "document"),
        author=payload.get("author", ""),
        updated_at=payload.get("updated_at", ""),
        metadata=payload.get("metadata", {}),
        authorized_principals=tuple(payload.get("authorized_principals", ("*",))),
        superseded=payload.get("superseded", False),
    )
    chunks = document_store.ingest(document)
    return {"document_id": document.document_id, "chunks": len(chunks), "version": document.version}


@app.post("/api/rag/search")
def search_documents(payload: dict[str, Any]) -> dict[str, Any]:
    result = rag_retriever.search(
        payload["query"],
        payload.get("principal_id", "system"),
        payload.get("entity_type"),
        payload.get("entity_id"),
        payload.get("max_results", 10),
    )
    return result.__dict__


@app.post("/api/rag/answer")
def answer_from_rag(payload: dict[str, Any]) -> dict[str, Any]:
    query = payload["query"]
    principal_id = payload.get("principal_id", "system")
    result = rag_retriever.search(query, principal_id, payload.get("entity_type"), payload.get("entity_id"), payload.get("max_results", 5))
    passages = result.data.get("passages", []) if isinstance(result.data, Mapping) else []
    context = tuple(f"[{item['chunk_id']}] {item['passage']}" for item in passages)
    response = model_provider.complete(ModelRequest(query, context, ("rag.search", "graph.search"))) if context else None
    return {"answer": response.text if response else "No authorized document passages matched the query.", "provider": response.provider if response else None, "model": response.model if response else None, "passages": passages, "graph_context": result.data.get("graph_context") if isinstance(result.data, Mapping) else None, "evidence_references": result.evidence_references, "warnings": result.warnings}


@app.get("/api/rag/documents/{document_id}")
def lookup_document(document_id: str, principal_id: str = "system") -> dict[str, Any]:
    return document_store.document_lookup(document_id, principal_id).__dict__


@app.post("/api/rag/policies/search")
def search_policies(payload: dict[str, Any]) -> dict[str, Any]:
    return document_store.policy_retrieve(
        payload["policy"], payload.get("principal_id", "system"), payload.get("max_results", 10)
    ).__dict__


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
        investigation = engine._load(investigation_id)
        metric, _, _ = resolve_metric(investigation.question)
        prepared = engine.plan(investigation_id, {"goal": "analyze_kpi", "metric": metric})
        tool_request = ToolRequest(
            tool_name="analytics.query",
            principal_id=prepared.principal_id,
            input={"metric": metric},
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


@app.post("/api/agent/investigate")
def investigate(payload: InvestigationRequest) -> dict[str, Any]:
    permission = PERMISSIONS(payload.principal_id, "analytics")
    if not permission.allowed:
        raise HTTPException(status_code=403, detail=permission.reason)
    investigation = engine.create(payload.prompt, payload.principal_id)
    plan = agent_pack.plan(payload.prompt, payload.principal_id, investigation.investigation_id)
    prepared = engine.plan(investigation.investigation_id, plan)
    metric, metric_label, metric_unit = resolve_metric(payload.prompt)
    tool_request = ToolRequest(
        tool_name="analytics.query",
        principal_id=prepared.principal_id,
        input={"metric": metric},
    )
    updated = engine.run_tools(investigation.investigation_id, [tool_request])
    engine.begin_validation(investigation.investigation_id)
    result = updated.tool_results[-1]
    value = result.data.get("value", 0) if isinstance(result.data, Mapping) else 0
    answer, facts, _ = format_metric_answer(metric, metric_label, value, metric_unit)
    finding = AgentFinding(
        agent_name=plan["agents"][0],
        answer=answer,
        facts=tuple(facts),
        evidence_ids=result.evidence_references,
        confidence="high" if result.status == "succeeded" else "low",
        limitations=result.warnings,
    )
    decision = agent_pack.decision_brief(investigation.investigation_id, (finding,))
    record = evidence_pipeline.build_record(
        updated,
        decision,
        required_claims=decision.facts,
        key_drivers=("Governed analytics result",),
        follow_up_questions=("Which site or segment contributes most to this result?",),
    )
    return {"plan": plan, "decision_record": record.__dict__, "tool_result": result.__dict__}


@app.post("/api/executive/brief")
def executive_brief(payload: ExecutiveBriefRequest):
    return build_executive_brief(payload.prompt, payload.principal_id, payload.conversation_id, payload.executive_role)


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict[str, Any]:
        return {"conversation_id": conversation_id, "messages": conversation_history.get(conversation_id, [])}
