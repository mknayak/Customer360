from decision_os.evidence import EvidencePipeline
from decision_os.models import DecisionBrief, Investigation, ToolResult


def _decision(**overrides):
    values = {
        "investigation_id": "inv-1",
        "answer": "Revenue increased.",
        "facts": ("Revenue increased",),
        "hypotheses": (),
        "recommendations": ("Increase inventory",),
        "evidence_ids": ("ev-1",),
        "confidence": "high",
    }
    values.update(overrides)
    return DecisionBrief(**values)


def _investigation(result: ToolResult) -> Investigation:
    investigation = Investigation("What happened to revenue?", "cfo-1")
    investigation.tool_results.append(result)
    return investigation


def test_pipeline_collects_tool_evidence_and_validates_record():
    investigation = _investigation(
        ToolResult(
            status="succeeded",
            data={"revenue": 120},
            source=("warehouse.daily_revenue",),
            freshness={"as_of": "2026-09-20T09:00:00Z"},
            query_metadata={"query_id": "q-1"},
            evidence_references=("ev-1",),
        )
    )

    record = EvidencePipeline().build_record(
        investigation,
        _decision(),
        required_claims=("Revenue increased",),
        key_drivers=("Higher completed orders",),
        follow_up_questions=("What changed by site?",),
    )

    assert record.status == "validated"
    assert record.recommendations == ("Increase inventory",)
    assert record.evidence[0].source == "warehouse.daily_revenue"
    assert record.evidence[0].query_reference == "q-1"
    assert record.key_drivers == ("Higher completed orders",)


def test_pipeline_blocks_recommendations_for_missing_stale_and_failed_evidence():
    investigation = Investigation("Why did revenue change?", "cfo-1")
    investigation.tool_results.extend(
        [
            ToolResult(status="succeeded", source=("warehouse",), freshness={"stale": True}, evidence_references=("ev-stale",)),
            ToolResult(status="denied", source=("finance",)),
        ]
    )

    record = EvidencePipeline().build_record(investigation, _decision(evidence_ids=("ev-missing",)))

    assert record.status == "blocked"
    assert record.recommendations == ()
    assert record.confidence == "low"
    assert any("stale" in limitation.lower() for limitation in record.limitations)
    assert any("denied" in limitation.lower() for limitation in record.limitations)
    assert any("not returned" in limitation.lower() for limitation in record.limitations)


def test_pipeline_surfaces_contradictions_and_rejects_causal_hypotheses():
    investigation = _investigation(
        ToolResult(status="succeeded", source=("warehouse",), evidence_references=("ev-1",))
    )
    decision = _decision(
        facts=("Revenue decreased",),
        hypotheses=("The promotion caused the decline",),
    )

    validation = EvidencePipeline().validate(investigation, decision, required_claims=("Revenue increased",))

    assert validation.passed is False
    assert validation.contradictions == ("Revenue increased",)
    assert validation.unsupported_causal_claims == ("The promotion caused the decline",)
    assert validation.confidence == "low"