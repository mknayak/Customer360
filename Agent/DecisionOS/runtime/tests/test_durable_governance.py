from decision_os.durable import SQLiteGraphStore, SQLiteSemanticRegistry
from decision_os.governance import AccessPolicy, GovernancePolicy
from decision_os.investigation import BoundedInvestigator
from decision_os.model_provider import DeterministicModelProvider
from decision_os.persistence import SQLitePersistence
from decision_os.models import Evidence
from decision_os.semantic import SemanticRegistry
from decision_os.workflow import WorkflowOrchestrator


def test_semantic_and_graph_adapters_survive_reopen(tmp_path):
    semantic = SQLiteSemanticRegistry(tmp_path / "decision.sqlite3")
    assert semantic.lookup("revenue").status == "resolved"
    semantic.close()

    graph = SQLiteGraphStore(tmp_path / "graph.sqlite3")
    graph.sync(
        [{"entity_type": "customer", "entity_id": "customer-1", "attributes": {"segment": "loyal"}}],
        [],
    )
    graph.close()
    reopened = SQLiteGraphStore(tmp_path / "graph.sqlite3")
    assert reopened.search("customer-1").data["entities"][0]["entity_id"] == "customer-1"
    reopened.close()


def test_persistence_and_governance_are_durable_and_fail_closed(tmp_path):
    persistence = SQLitePersistence(tmp_path / "decision.sqlite3")
    persistence.append_audit("decision-1", "cfo-1", "read", {"resource": "finance"})
    assert persistence.audit("decision-1")[0]["action"] == "read"
    evidence = Evidence("evidence-1", "Revenue is 100", "analytics", synthetic=True)
    persistence.save_evidence(evidence)
    assert persistence.get_evidence("evidence-1").claim == "Revenue is 100"
    persistence.save_memory("memory-1", "cfo-1", {"note": "temporary"}, "2026-01-01T00:00:00+00:00")
    assert persistence.purge_expired_memory("2026-01-02T00:00:00+00:00") == 1
    persistence.close()

    policy = GovernancePolicy({"cfo-1": AccessPolicy("cfo-1", frozenset({"customer"}), frozenset({"email"}), consent_required=True)})
    assert policy.project("cfo-1", "customer", {"customer_id": "c1", "email": "secret"}, consent_granted=True)["email"] == "[MASKED]"
    try:
        policy.project("unknown", "customer", {})
    except PermissionError:
        pass
    else:
        raise AssertionError("unknown principal must be denied")


def test_bounded_investigator_resolves_metric_and_is_idempotent(tmp_path):
    persistence = SQLitePersistence(tmp_path / "workflow.sqlite3")
    investigator = BoundedInvestigator(SemanticRegistry(), DeterministicModelProvider(), WorkflowOrchestrator(persistence))
    plan = investigator.plan("How is revenue performing?", "revenue")
    calls = []
    actions = {"permission-check": lambda: calls.append("permission"), "semantic-lookup": lambda: calls.append("semantic"), "analytics-query": lambda: calls.append("analytics"), "evidence-validation": lambda: calls.append("evidence")}
    first = investigator.run("investigation-1", plan, actions)
    second = investigator.run("investigation-1", plan, actions)
    assert first.status == "completed"
    assert second.workflow_id == first.workflow_id
    assert calls == ["permission", "semantic", "analytics", "evidence"]
    persistence.close()
