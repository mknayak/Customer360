import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "Agent" / "DecisionOS" / "runtime"))
sys.path.insert(0, str(ROOT))

from Agent.app.main import app  # noqa: E402


def test_health_ok():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ui_route_renders_prompt_box():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    html = response.text.lower()
    assert "customer360" in html
    assert "prompt" in html


def test_chat_endpoint_runs_investigation_from_prompt():
    client = TestClient(app)
    response = client.post(
        "/api/agent/chat",
        json={"prompt": "Why did revenue fall?", "principal_id": "cfo-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"running", "completed", "validating"}
    assert body["answer"]
    assert body["investigation_id"]


def test_create_and_run_investigation():
    client = TestClient(app)
    response = client.post(
        "/api/investigations",
        json={"question": "Why did revenue fall?", "principal_id": "cfo-1"},
    )
    assert response.status_code == 200
    investigation_id = response.json()["investigation_id"]

    run_response = client.post(f"/api/investigations/{investigation_id}/run")
    assert run_response.status_code == 200
    body = run_response.json()
    assert body["status"] in {"running", "completed", "validating"}
    assert "tool_results" in body
