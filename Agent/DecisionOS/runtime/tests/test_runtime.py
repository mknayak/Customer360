from decision_os.engine import InvestigationEngine
from decision_os.evaluation import DecisionEvaluator
from decision_os.models import (
    DecisionBrief,
    InvestigationStatus,
    PermissionDecision,
    ToolRequest,
)
from decision_os.persistence import InMemoryPersistence
from decision_os.tools import ToolDispatcher, ToolSpec


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
