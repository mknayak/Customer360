from decision_os.engine import InvestigationEngine
from decision_os.agents import AgentFinding, AgentPack
from decision_os.semantic import SemanticRegistry
from decision_os.evaluation import DecisionEvaluator
from decision_os.catalog import TOOL_CATALOG, catalog_contract, register_tool_catalog
from decision_os.models import (
    DecisionBrief,
    InvestigationStatus,
    PermissionDecision,
    ToolRequest,
)
from decision_os.persistence import InMemoryPersistence
from decision_os.tools import PermissionMap, ToolDispatcher, ToolExecution, ToolSpec


def allow_all(principal_id: str, resource: str) -> PermissionDecision:
    return PermissionDecision(True, principal_id, resource, "allowed")


def deny_finance(principal_id: str, resource: str) -> PermissionDecision:
    allowed = resource != "finance"
    reason = "allowed" if allowed else "finance access denied"
    return PermissionDecision(allowed, principal_id, resource, reason)


def build_engine(checker=allow_all):
    dispatcher = ToolDispatcher(checker)
    dispatcher.register(
        ToolSpec(
            name="analytics.query",
            description="Return a deterministic metric",
            resource="analytics",
            handler=lambda inputs: {"revenue": inputs["value"]},
        )
    )
    return InvestigationEngine(InMemoryPersistence(), dispatcher)


def test_investigation_lifecycle_and_tool_result():
    engine = build_engine()
    investigation = engine.create("What happened to revenue?", "cfo-1")
    engine.plan(investigation.investigation_id, {"metric": "revenue"})
    running = engine.run_tools(
        investigation.investigation_id,
        [ToolRequest("analytics.query", "cfo-1", {"value": 120})],
    )
    assert running.status == InvestigationStatus.RUNNING
    assert running.tool_results[0].data == {"revenue": 120}
    assert engine.begin_validation(investigation.investigation_id).status == InvestigationStatus.VALIDATING
    assert engine.complete(investigation.investigation_id).status == InvestigationStatus.COMPLETED


def test_dispatcher_denies_before_handler_runs():
    called = False

    def handler(_inputs):
        nonlocal called
        called = True
        return {"secret": "value"}

    dispatcher = ToolDispatcher(deny_finance)
    dispatcher.register(ToolSpec("finance.query", "finance", handler, "finance"))
    result = dispatcher.dispatch(ToolRequest("finance.query", "ceo-1", {}))
    assert result.status == "denied"
    assert called is False


def test_dispatcher_validates_input_and_returns_provenance_envelope():
    dispatcher = ToolDispatcher(PermissionMap({"cfo-1": {"analytics"}}))
    dispatcher.register(
        ToolSpec(
            name="analytics.query",
            description="Query a governed metric",
            handler=lambda _inputs: ToolExecution(
                data={"revenue": 120},
                source=("warehouse.daily_revenue",),
                definition=("revenue.v1",),
                filters={"period": "2026-W38"},
                freshness={"as_of": "2026-09-20T09:00:00Z"},
                query_metadata={"query_id": "q-1"},
                evidence_references=("ev-1",),
            ),
            resource="analytics",
            input_schema={
                "required": ("metric",),
                "properties": {"metric": {"type": "string"}},
            },
        )
    )
    result = dispatcher.dispatch(ToolRequest("analytics.query", "cfo-1", {"metric": "revenue"}))
    assert result.status == "succeeded"
    assert result.source == ("warehouse.daily_revenue",)
    assert result.definition == ("revenue.v1",)
    assert result.filters == {"period": "2026-W38"}
    assert result.query_metadata == {"query_id": "q-1"}
    assert result.evidence_references == ("ev-1",)

    invalid = dispatcher.dispatch(ToolRequest("analytics.query", "cfo-1", {}))
    assert invalid.status == "failed"
    assert invalid.warnings == ("Missing required tool input: metric",)


def test_permission_map_fails_closed_for_unknown_principal():
    decision = PermissionMap({"cfo-1": {"analytics"}})("unknown", "analytics")
    assert decision.allowed is False


def test_catalog_registers_only_allowlisted_tools_with_contracts():
    dispatcher = ToolDispatcher(PermissionMap({"cfo-1": {"analytics"}}))
    handlers = {contract.name: lambda _inputs: {"ok": True} for contract in TOOL_CATALOG}
    register_tool_catalog(dispatcher, handlers)

    assert {spec.name for spec in dispatcher.specs()} == {
        contract.name for contract in TOOL_CATALOG
    }
    assert catalog_contract("analytics.query").input_schema["required"] == ("metric",)


def test_catalog_rejects_uncataloged_handler_names():
    dispatcher = ToolDispatcher(PermissionMap({"cfo-1": {"analytics"}}))
    try:
        register_tool_catalog(dispatcher, {"customers.delete": lambda _inputs: None})
    except ValueError as error:
        assert "not in the DecisionOS catalog" in str(error)
    else:
        raise AssertionError("Uncataloged handler was registered")


def test_evaluator_reports_missing_expected_claims():
    decision = DecisionBrief(
        investigation_id="inv-1",
        answer="Revenue increased.",
        facts=("Revenue increased",),
        hypotheses=(),
        recommendations=(),
        evidence_ids=("ev-1",),
        confidence="medium",
    )
    result = DecisionEvaluator().evaluate(decision, ("Revenue increased", "Margin decreased"))
    assert result.passed is False
    assert result.matched_claims == ("Revenue increased",)
    assert result.missing_claims == ("Margin decreased",)
    assert result.contradictions == ()
    assert result.confidence == "medium"


def test_evaluator_reports_contradictions_and_low_confidence():
    decision = DecisionBrief(
        investigation_id="inv-2",
        answer="Revenue decreased.",
        facts=("Revenue decreased",),
        hypotheses=(),
        recommendations=(),
        evidence_ids=("ev-2",),
        confidence="low",
    )
    result = DecisionEvaluator().evaluate(decision, ("Revenue increased",))
    assert result.passed is False
    assert result.matched_claims == ()
    assert result.missing_claims == ("Revenue increased",)
    assert result.contradictions == ("Revenue increased",)
    assert result.confidence == "low"


def test_evaluator_assigns_high_confidence_when_all_claims_match():
    decision = DecisionBrief(
        investigation_id="inv-3",
        answer="Revenue increased and margin improved.",
        facts=("Revenue increased", "Margin improved"),
        hypotheses=(),
        recommendations=(),
        evidence_ids=("ev-3",),
        confidence="high",
    )
    result = DecisionEvaluator().evaluate(
        decision,
        ("Revenue increased", "Margin improved"),
    )
    assert result.passed is True
    assert result.confidence == "high"


def test_agent_pack_routes_questions_and_adds_validator():
    pack = AgentPack()
    plan = pack.plan("Why did mobile cart conversion fall after the promotion?", "cfo-1", "inv-1")

    assert plan["agents"] == ("promotion-intelligence", "digital-intelligence", "evidence-validator")
    assert "analytics.query" in plan["required_tools"]


def test_agent_pack_downgrades_findings_without_evidence():
    finding = AgentPack().validate_finding(
        AgentFinding("customer-intelligence", "Retention changed.", confidence="high")
    )

    assert finding.confidence == "low"
    assert "No evidence references supplied" in finding.limitations


def test_agent_pack_builds_evidence_backed_decision_brief():
    brief = AgentPack().decision_brief(
        "inv-1",
        (AgentFinding("product-intelligence", "Demand increased.", facts=("Demand increased",), evidence_ids=("ev-1",), confidence="high"),),
    )

    assert brief.evidence_ids == ("ev-1",)
    assert brief.confidence == "high"


def test_semantic_registry_resolves_metric_alias_with_governance_metadata():
    result = SemanticRegistry().lookup("cart abandonment")

    assert result.status == "resolved"
    assert result.definitions[0].metric_id == "customer360.cart-abandonment"
    assert result.definitions[0].formula == "abandoned carts / eligible carts"
    assert result.definitions[0].owner == "digital"


def test_semantic_registry_surfaces_missing_and_stale_definitions():
    registry = SemanticRegistry()

    assert registry.lookup("unknown metric").status == "not_found"
    stale = registry.lookup("revenue", as_of=__import__("datetime").datetime(2026, 9, 22, tzinfo=__import__("datetime").timezone.utc))
    assert stale.status == "stale"
    assert stale.warnings


def test_semantic_lookup_execution_returns_provenance_and_evidence_reference():
    result = SemanticRegistry().lookup_execution({"term": "conversion rate", "context": {"team": "digital"}})

    assert result.data["status"] == "resolved"
    assert result.source == ("customer360.semantic.metric_registry",)
    assert result.definition == ("v1",)
    assert result.evidence_references == ("metric-definition:customer360.conversion",)
