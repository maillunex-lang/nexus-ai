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

def test_mcp_initialize():
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "nexus-test", "version": "1"}}}
    with TestClient(app) as client:
        r = client.post("/mcp/", json=payload, headers={"Accept": "application/json, text/event-stream"})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["serverInfo"]["name"] == "NEXUS AI"

def test_mcp_tool_catalog():
    payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    with TestClient(app) as client:
        r = client.post("/mcp/", json=payload, headers={"Accept": "application/json, text/event-stream"})
    assert r.status_code == 200, r.text
    names = {tool["name"] for tool in r.json()["result"]["tools"]}
    assert {"nexus_status", "nexus_capabilities"} <= names
