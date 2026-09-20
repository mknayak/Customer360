"""Allow-listed DecisionOS tool contracts and registration helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .tools import ToolDispatcher, ToolHandler, ToolSpec


@dataclass(frozen=True)
class ToolContract:
    name: str
    description: str
    resource: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any] = field(default_factory=lambda: {"type": "object"})
    read_only: bool = True
    timeout_seconds: float = 5.0
    retry_limit: int = 0


def _schema(*required: str, **properties: str) -> dict[str, Any]:
    return {
        "required": required,
        "properties": {name: {"type": value} for name, value in properties.items()},
    }


TOOL_CATALOG: tuple[ToolContract, ...] = (
    ToolContract("customer.snapshot", "Retrieve an authorized cross-service customer snapshot.", "customer", _schema("customer_id", customer_id="string")),
    ToolContract("analytics.query", "Run a governed analytical query.", "analytics", _schema("metric", metric="string")),
    ToolContract("analytics.segment", "Compare a metric by approved segment.", "analytics", _schema("metric", "segment", metric="string", segment="string")),
    ToolContract("analytics.funnel", "Calculate an approved funnel.", "analytics", _schema("funnel", funnel="string")),
    ToolContract("analytics.compare_periods", "Compare a metric across periods.", "analytics", _schema("metric", "current_period", "prior_period", metric="string", current_period="string", prior_period="string")),
    ToolContract("semantic.lookup", "Resolve a governed business term.", "semantic", _schema("term", term="string")),
    ToolContract("semantic.metric_definition", "Retrieve a metric definition.", "semantic", _schema("metric", metric="string")),
    ToolContract("semantic.entity_mapping", "Resolve an entity identifier.", "semantic", _schema("entity_type", "entity_id", entity_type="string", entity_id="string")),
    ToolContract("graph.search", "Search approved entity relationships.", "graph", _schema("query", query="string", max_results="integer")),
    ToolContract("graph.neighbors", "Retrieve approved entity neighbors.", "graph", _schema("entity_type", "entity_id", entity_type="string", entity_id="string", relationship_types="array", max_results="integer")),
    ToolContract("graph.paths", "Find an approved relationship path.", "graph", _schema("from_id", "to_id", from_id="string", to_id="string", max_depth="integer")),
    ToolContract("graph.relationship_summary", "Summarize entity relationships.", "graph", _schema("entity_type", "entity_id", entity_type="string", entity_id="string")),
    ToolContract("rag.search", "Retrieve authorized document passages.", "rag", _schema("query", query="string", principal_id="string", entity_type="string", entity_id="string", max_results="integer")),
    ToolContract("rag.document_lookup", "Retrieve an authorized document.", "rag", _schema("document_id", document_id="string")),
    ToolContract("rag.policy_retrieve", "Retrieve an authorized policy.", "rag", _schema("policy", policy="string")),
    ToolContract("permission.check", "Check access to a resource.", "governance", _schema("principal_id", "resource", principal_id="string", resource="string")),
    ToolContract("decision.evaluate", "Evaluate decision claims and evidence.", "governance", _schema("decision", "required_claims", decision="object", required_claims="array")),
    ToolContract("decision.record", "Persist a validated evidence-backed decision record.", "governance", _schema("investigation_id", "decision_brief", investigation_id="string", decision_brief="object", required_claims="array", key_drivers="array", follow_up_questions="array")),
    ToolContract("lineage.explain", "Explain source and freshness metadata.", "governance", _schema("source", source="string")),
)

_CONTRACTS_BY_NAME = {contract.name: contract for contract in TOOL_CATALOG}


def register_tool_catalog(
    dispatcher: ToolDispatcher,
    handlers: Mapping[str, ToolHandler],
) -> None:
    """Register only cataloged tools whose governed handlers are available."""

    unknown_handlers = set(handlers) - set(_CONTRACTS_BY_NAME)
    if unknown_handlers:
        names = ", ".join(sorted(unknown_handlers))
        raise ValueError(f"Handlers are not in the DecisionOS catalog: {names}")

    for name, handler in handlers.items():
        contract = _CONTRACTS_BY_NAME[name]
        dispatcher.register(
            ToolSpec(
                name=contract.name,
                description=contract.description,
                handler=handler,
                resource=contract.resource,
                read_only=contract.read_only,
                input_schema=contract.input_schema,
                output_schema=contract.output_schema,
                timeout_seconds=contract.timeout_seconds,
                retry_limit=contract.retry_limit,
            )
        )


def catalog_contract(name: str) -> ToolContract:
    try:
        return _CONTRACTS_BY_NAME[name]
    except KeyError as error:
        raise KeyError(f"Unknown DecisionOS tool contract: {name}") from error
