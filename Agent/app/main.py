from __future__ import annotations

import json
import os
import re
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
    dimensions = tuple(inputs.get("dimensions", ()))
    filters = dict(inputs.get("filters", {}))
    joins = tuple(inputs.get("joins", ()))
    granularity = inputs.get("granularity")
    profile_dimension = inputs.get("profile_dimension")
    origin = os.getenv("DATA_PLATFORM_ORIGIN", "http://127.0.0.1:8010")
    try:
        ingest_request = Request(f"{origin.rstrip('/')}/api/ingest/event-service", data=b"", method="POST")
        with urlopen(ingest_request, timeout=5):
            pass
        if profile_dimension:
            query_payload = json.dumps({"principal_id": inputs["principal_id"], "dimension": profile_dimension}).encode()
            query_request = Request(f"{origin.rstrip('/')}/api/payment-failures/by-profile", data=query_payload, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(query_request, timeout=15) as response:
                result = json.loads(response.read())
            result = {**result, "value": result["rows"]}
            source = "data-platform:/api/payment-failures/by-profile"
        elif granularity:
            query_payload = json.dumps({"principal_id": inputs.get("principal_id", "cfo-1"), "metric": metric, "granularity": granularity}).encode()
            query_request = Request(f"{origin.rstrip('/')}/api/trends", data=query_payload, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(query_request, timeout=5) as response:
                result = json.loads(response.read())
            result = {**result, "value": result["points"]}
            source = "data-platform:/api/trends"
        elif dimensions or filters or joins:
            query_payload = json.dumps({"principal_id": inputs.get("principal_id", "cfo-1"), "metric": metric, "dimensions": dimensions, "filters": filters, "joins": joins, "order": inputs.get("order", "desc"), "limit": inputs.get("limit", 25)}).encode()
            query_request = Request(f"{origin.rstrip('/')}/api/semantic-query/execute", data=query_payload, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(query_request, timeout=5) as response:
                result = json.loads(response.read())
            rows = result.get("rows", [])
            result = {**result, "value": rows if dimensions else (rows[0].get("value", 0) if rows else 0)}
            source = f"data-platform:/api/semantic-query/execute"
        else:
            with urlopen(f"{origin.rstrip('/')}/api/kpis/{metric}", timeout=5) as response:
                result = json.loads(response.read())
            source = f"data-platform:/api/kpis/{metric}"
        return ToolExecution(
            data={**result, "status": "resolved"},
            source=(source,),
            query_metadata={"tool": "analytics.query", "metric": metric, "dimensions": dimensions, "filters": filters, "joins": joins, "granularity": granularity, "profile_dimension": profile_dimension, "live": True},
            freshness={"retrieved_at": "live"},
            evidence_references=(f"analytics:{metric}",),
        )
    except (URLError, OSError, json.JSONDecodeError):
        if profile_dimension:
            return ToolExecution(
                data={"metric": metric, "value": [], "status": "unavailable"},
                source=("data-platform:/api/payment-failures/by-profile",),
                query_metadata={"tool": "analytics.query", "metric": metric, "profile_dimension": profile_dimension, "live": False},
                warnings=("Live payment failures and CRM profiles unavailable; no customer comparison can be calculated",),
            )
        if granularity:
            return ToolExecution(
                data={"metric": metric, "value": [], "status": "unavailable"},
                source=("data-platform:/api/trends",),
                query_metadata={"tool": "analytics.query", "metric": metric, "granularity": granularity, "live": False},
                warnings=("Live Data Platform unavailable; no period comparison can be calculated",),
            )
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
    if "payment" in normalized and any(keyword in normalized for keyword in ("fail", "failure", "declin")):
        return "payment_failures", "Payment failures", "failures"
    candidates = (
        ("page_popularity", "Most visited page", "pages"),
        ("page_dropoff", "Most dropped page", "pages"),
        ("product_performance", "Product performance", "results"),
        ("average_cart_value", "Average cart value", "USD"),
        ("payment_failures", "Payment failures", "failures"),
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
        "average_cart_value": ("average cart value", "avg cart value", "average order value", "average cart"),
        "payment_failures": ("payment failed", "payment failure", "failed payment", "payments failed", "declined payment"),
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


def select_metric_with_model(prompt: str) -> tuple[tuple[str, str, str], str, dict[str, Any]]:
    """Let the configured model select one governed analytics metric."""
    normalized = prompt.casefold()
    if resolve_metric(prompt)[0] == "payment_failures" and any(word in normalized for word in ("customer", "country", "location", "age group")):
        dimension = "age_group" if "age" in normalized else "country"
        return ("payment_failures", "Payment failures", "failures"), "deterministic", {"profile_dimension": dimension}
    if not isinstance(model_provider, OpenAICompatibleModelProvider):
        selection = resolve_metric(prompt)
        granularity = trend_granularity(prompt)
        if granularity:
            return selection, "deterministic", {"granularity": granularity}
        if selection[0] == "product_performance" and "customer" in prompt.casefold():
            return selection, "deterministic", {"dimensions": ["customer", "product"], "filters": {}, "joins": ["orders"], "order": "desc", "limit": 25}
        if selection[0] == "payment_failures":
            normalized = prompt.casefold()
            dimensions = []
            if "customer" in normalized:
                dimensions.append("customer")
            if "reason" in normalized:
                dimensions.append("failure_reason")
            if "period" in normalized or "day" in normalized or "date" in normalized:
                dimensions.append("period")
            if dimensions:
                return selection, "deterministic", {"dimensions": dimensions, "filters": {}, "joins": [], "order": "desc", "limit": 25}
        return selection, "deterministic", {}

    metric_options = (
        "revenue, visits, conversion, cart_abandonment, retention, segment_conversion, "
        "product_performance, average_cart_value, page_popularity, page_dropoff, payment_failures"
    )
    granularity = trend_granularity(prompt)
    request = ModelRequest(
        question=prompt,
        context=(
            f"Available governed metrics: {metric_options}",
            'Return JSON only with this shape: {"tool":"analytics.query","query":{"metric":"<one available metric>","dimensions":[],"filters":{},"joins":[],"order":"desc","limit":25}}',
            'The product_performance metric supports the governed join "orders" when the question asks for customer-level product analysis.',
            "Select payment_failures for questions about failed, declined, or rejected payments.",
            "Only use dimensions and filters supported by the selected metric; use empty arrays/objects when none are needed.",
        ),
        allowed_tools=("analytics.query",),
        max_output_tokens=120,
        response_format={"type": "json_object"},
    )
    try:
        response = model_provider.complete(request)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.removeprefix("```").removeprefix("json").removesuffix("```").strip()
        selection = json.loads(text)
        query = selection.get("query", selection)
        metric = query.get("metric")
        dimensions = query.get("dimensions", [])
        filters = query.get("filters", {})
        joins = query.get("joins", [])
        order = query.get("order", "desc")
        limit = query.get("limit", 25)
        if selection.get("tool") != "analytics.query" or metric not in metric_options.split(", "):
            raise ValueError("Model selected an unavailable analytics tool or metric")
        if not isinstance(dimensions, list) or not all(isinstance(item, str) for item in dimensions) or not isinstance(filters, dict) or not isinstance(joins, list) or not all(isinstance(item, str) for item in joins) or order not in {"asc", "desc"} or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("Model returned an invalid semantic query")
        labels = {
            "revenue": ("Revenue", "USD"),
            "visits": ("Visits", "visits"),
            "conversion": ("Conversion rate", "%"),
            "cart_abandonment": ("Cart abandonment", "%"),
            "retention": ("Customer retention", "%"),
            "segment_conversion": ("Segment conversion", "results"),
            "product_performance": ("Product performance", "results"),
            "average_cart_value": ("Average cart value", "USD"),
            "page_popularity": ("Most visited page", "pages"),
            "page_dropoff": ("Most dropped page", "pages"),
            "payment_failures": ("Payment failures", "failures"),
        }
        label, unit = labels[metric]
        if granularity:
            return (metric, label, unit), response.model, {"granularity": granularity}
        return (metric, label, unit), response.model, {"dimensions": dimensions, "filters": filters, "joins": joins, "order": order, "limit": limit}
    except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError):
        if granularity:
            return resolve_metric(prompt), "model-fallback", {"granularity": granularity}
        return ("revenue", "Revenue", "USD"), "model-fallback", {}


def trend_granularity(prompt: str) -> str | None:
    normalized = prompt.casefold()
    if not re.search(r"\b(trend|trends|over time|vary by period|varies by period|change over time|changed over time|changes over time|compare periods|compared to prior|growth over time|by day|by week|by month|daily|weekly|monthly|prior period)\b", normalized):
        return None
    if re.search(r"\b(day|daily)\b", normalized):
        return "day"
    if re.search(r"\b(week|weekly)\b", normalized):
        return "week"
    return "month"


def format_trend_answer(label: str, unit: str, points: list[dict[str, Any]], granularity: str) -> tuple[str, list[str], list[str]]:
    available = [point for point in points if point.get("value") is not None]
    if not available:
        return (f"There is not enough {granularity}-level data to compare {label.lower()} across periods.",
                ["No comparable periods with a defined value are available."], [])
    def display(value: float) -> str:
        return f"{value * 100:.2f}%" if unit == "%" else f"${value:,.2f}" if unit == "USD" else f"{value:,.0f}"
    first, last = available[0], available[-1]
    if len(available) < 2:
        answer = f"{label} was {display(last['value'])} in {last['period']}; there is not enough data to establish a trend."
    else:
        delta = last["value"] - first["value"]
        difference = f"{abs(delta) * 100:.2f} percentage points" if unit == "%" else display(abs(delta))
        direction = "increased" if delta > 0 else "decreased" if delta < 0 else "was unchanged"
        answer = f"{label} {direction} from {display(first['value'])} in {first['period']} to {display(last['value'])} in {last['period']}"
        answer += f" ({difference})" if delta else "."
    facts = [f"{point['period']}: {display(point['value'])}" for point in available]
    return answer, facts, []


def format_profile_answer(rows: list[dict[str, Any]], dimension: str) -> tuple[str, list[str], list[str]]:
    label = "country" if dimension == "country" else "age group"
    if not rows:
        return (f"No reportable payment failure breakdown by {label} is available.", [], [])
    if len(rows) == 1:
        answer = f"Only one {label} has a reportable payment failure count: {rows[0]['group']} ({rows[0]['value']:,} events). No group comparison can be made."
    else:
        answer = f"Payment failures by {label} are highest for {rows[0]['group']} ({rows[0]['value']:,} events), compared with {rows[1]['group']} ({rows[1]['value']:,} events)."
    return answer, [f"{row['group']}: {row['value']:,} PaymentFailed events" for row in rows], []


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
    if metric == "payment_failures":
        numeric = int(value or 0)
        answer = f"There have been {numeric:,} payment failures."
        facts = [f"Payment failures resolved to {numeric:,} PaymentFailed events."]
        return answer, facts, ["What is the most common payment failure reason?", "How do payment failures vary by period?"]
    numeric = float(value or 0)
    display_value = numeric * 100 if unit == "%" else numeric
    formatted = f"{display_value:,.2f}" if unit in {"USD", "%"} else f"{display_value:,.0f}"
    suffix = "%" if unit == "%" else f" {unit}" if unit else ""
    answer = f"{label} is currently {formatted}{suffix}."
    facts = [f"{label} resolved to {formatted}{suffix}."]
    follow_ups = {
        "revenue": ["Which site or segment contributes most to revenue?", "How does revenue compare with the prior period?"],
        "payment_failures": ["What is the most common payment failure reason?", "How do payment failures vary by period?"],
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
    granularity: Literal["day", "week", "month"] | None = None
    profile_dimension: Literal["country", "age_group"] | None = None


class InvestigationRequest(ChatRequest):
    time_period: str | None = None


conversation_history: dict[str, list[dict[str, str]]] = {}
TEMPLATE_PATH = Path(__file__).parent / "templates" / "index.html"


def build_executive_brief(
    prompt: str,
    principal_id: str,
    conversation_id: str | None = None,
    executive_role: str = "CFO",
    granularity: str | None = None,
    profile_dimension: str | None = None,
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

    (metric, metric_label, metric_unit), planner_model, query_spec = select_metric_with_model(prompt)
    if granularity is not None:
        query_spec = {"granularity": granularity}
    if profile_dimension is not None:
        if metric != "payment_failures":
            raise HTTPException(status_code=400, detail="Customer profile breakdown is only available for payment failures")
        query_spec = {"profile_dimension": profile_dimension}
    add_step(
        "Understood the question",
        f"Read \"{prompt}\" and mapped the language to the governed metric '{metric_label}'.",
        {"metric": metric, "query": query_spec, "planner": planner_model, "executive_role": executive_role},
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
        input={"metric": metric, "principal_id": prepared.principal_id, **query_spec},
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
    granularity = query_spec.get("granularity")
    profile_dimension = query_spec.get("profile_dimension")
    if profile_dimension:
        answer, facts, follow_up_questions = format_profile_answer(value if isinstance(value, list) else [], profile_dimension)
    elif granularity:
        points = value if isinstance(value, list) else []
        answer, facts, follow_up_questions = format_trend_answer(metric_label, metric_unit, points, granularity)
    else:
        answer, facts, follow_up_questions = format_metric_answer(metric, metric_label, value, metric_unit)
    add_step(
        "Analyzed the data",
        f"Interpreted the returned value for '{metric_label}' and drafted facts, hypotheses, and next actions.",
        {"facts_extracted": len(facts)},
    )

    model_used = "deterministic"
    if isinstance(model_provider, OpenAICompatibleModelProvider) and not granularity and not profile_dimension:
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
    limitations = [] if live else ["Live Data Platform unavailable; period comparison could not be calculated." if granularity else "Live Data Platform unavailable; deterministic analytics fallback was used."]
    if profile_dimension:
        limitations = ["Live Data Platform or CRM profiles unavailable; no customer comparison can be calculated."] if not live else ["Counts use current CRM profiles, not historical attributes; they are not payment failure rates and do not establish demographic risk."]
        if live and result.data.get("unmatched_events"):
            limitations.append(f"{result.data['unmatched_events']:,} failure events could not be matched to a {profile_dimension.replace('_', ' ')}.")
        if live and result.data.get("suppressed_groups"):
            limitations.append("Groups with fewer than three distinct customers are excluded from this breakdown.")
        if live and len(value) < 2:
            limitations.append("Fewer than two reportable groups are available; no group comparison can be established.")
    if granularity and metric == "retention":
        limitations.append("Period retention compares customers with successful orders in adjacent calendar periods; it is not the all-time repeat-purchase KPI.")
    if granularity and len([point for point in value if point.get("value") is not None]) < 2:
        limitations.append("Fewer than two comparable period values are available; no trend can be established.")
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
        "limitations": limitations,
            "recommendations": [] if granularity or profile_dimension else ["Drill into revenue by site, period, or customer segment before taking action."],
            "follow_up_questions": follow_up_questions,
                "metrics": [{"label": metric_label, "value": value, "unit": metric_unit, "trend": 0.0}],
            "time_series": {"metric": metric, "label": metric_label, "unit": metric_unit, "granularity": granularity, "points": value, "definition": result.data.get("definition", ""), "source": source_label} if granularity and live else None,
            "profile_breakdown": {"dimension": profile_dimension, "rows": value, "definition": result.data.get("definition", ""), "source": source_label} if profile_dimension else None,
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
    return build_executive_brief(payload.prompt, payload.principal_id, payload.conversation_id, payload.executive_role, payload.granularity, payload.profile_dimension)


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict[str, Any]:
        return {"conversation_id": conversation_id, "messages": conversation_history.get(conversation_id, [])}
