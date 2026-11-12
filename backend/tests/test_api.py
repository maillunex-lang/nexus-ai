from fastapi.testclient import TestClient
from nexus.main import app

def test_health():
    with TestClient(app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_status(monkeypatch):
    monkeypatch.setattr("nexus.main.database_ok", lambda: False)
    with TestClient(app) as client:
        r = client.get("/api/status")
    assert r.status_code == 200
    assert r.json()["database"] == "unavailable"
    assert r.json()["security"] == "development-only"
