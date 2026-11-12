import pytest
from fastapi.testclient import TestClient
from nexus.main import app

@pytest.fixture(scope="module")
def client():
    # FastMCP's session manager can only be started once per app instance.
    with TestClient(app, base_url="http://localhost") as test_client:
        yield test_client

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_status(client, monkeypatch):
    monkeypatch.setattr("nexus.main.database_ok", lambda: False)
    r = client.get("/api/status")
    assert r.status_code == 200
    assert r.json()["database"] == "unavailable"
    assert r.json()["security"] == "internal-only"

def test_mcp_initialize(client, monkeypatch):
    monkeypatch.setenv("NEXUS_MCP_INTERNAL_TOKEN", "test-only-secret-" + "x"*40)
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "nexus-test", "version": "1"}}}
    r = client.post("/mcp/", json=payload, headers={"Accept": "application/json, text/event-stream", "Authorization": "Bearer test-only-secret-" + "x"*40})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["serverInfo"]["name"] == "NEXUS AI"

def test_mcp_tool_catalog(client, monkeypatch):
    monkeypatch.setenv("NEXUS_MCP_INTERNAL_TOKEN", "test-only-secret-" + "x"*40)
    payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    r = client.post("/mcp/", json=payload, headers={"Accept": "application/json, text/event-stream", "Authorization": "Bearer test-only-secret-" + "x"*40})
    assert r.status_code == 200, r.text
    names = {tool["name"] for tool in r.json()["result"]["tools"]}
    assert {"nexus_status", "nexus_capabilities"} <= names
