from fastapi.testclient import TestClient
from nexus.main import app


def test_agents_requires_login():
    response = TestClient(app).get("/api/agents")
    assert response.status_code == 401


def test_agents_denies_user_without_role(monkeypatch):
    monkeypatch.setattr("nexus.agents.current_user", lambda request: {"roles": []})
    response = TestClient(app).get("/api/agents")
    assert response.status_code == 403


def test_agents_registry_does_not_claim_execution(monkeypatch):
    monkeypatch.setattr("nexus.agents.current_user", lambda request: {"roles": ["owner"]})
    response = TestClient(app).get("/api/agents")
    assert response.status_code == 200
    body = response.json()
    assert body["execution_enabled"] is False
    assert len(body["agents"]) == 5
    assert all(a["status"] == "planned" and a["execution_enabled"] is False for a in body["agents"])
