from decision_os.models import ToolResult
from decision_os.persistence import InMemoryPersistence
from decision_os.workflow import WorkflowOrchestrator, WorkflowStep
from threading import Event


def test_workflow_retries_steps_collects_evidence_and_is_idempotent():
    persistence = InMemoryPersistence()
    orchestrator = WorkflowOrchestrator(persistence)
    attempts = 0

    def flaky_step():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary failure")
        return ToolResult(status="succeeded", evidence_references=("ev-1",))

    first = orchestrator.run(
        "inv-1",
        (WorkflowStep("retrieve", flaky_step, retry_limit=1),),
        idempotency_key="request-1",
    )
    replay = orchestrator.run(
        "inv-1",
        (WorkflowStep("retrieve", flaky_step, retry_limit=1),),
        idempotency_key="request-1",
    )

    assert first.status == "completed"
    assert first.steps[0].attempts == 2
    assert first.evidence_references == ["ev-1"]
    assert replay.workflow_id == first.workflow_id
    assert attempts == 2
    assert first.summary()["completed_steps"] == ("retrieve",)


def test_workflow_times_out_and_compensates_completed_steps():
    persistence = InMemoryPersistence()
    orchestrator = WorkflowOrchestrator(persistence)
    compensation_calls = []

    def fail_step():
        Event().wait(0.05)

    result = orchestrator.run(
        "inv-2",
        (
            WorkflowStep("reserve", lambda: "reserved", compensation=lambda: compensation_calls.append("reserve")),
            WorkflowStep("checkout", fail_step, retry_limit=1, timeout_seconds=0.001),
            WorkflowStep("never-runs", lambda: "unexpected"),
        ),
    )

    assert result.status == "failed"
    assert [step.name for step in result.steps] == ["reserve", "checkout"]
    assert result.steps[1].attempts == 2
    assert compensation_calls == ["reserve"]
    assert "compensated step reserve" in result.audit_events
    assert result.summary()["failed_steps"] == ("checkout",)