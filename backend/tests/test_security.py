from fastapi.testclient import TestClient
from nexus.main import app


def test_mcp_denied_without_secret(monkeypatch):
    monkeypatch.delenv("NEXUS_MCP_INTERNAL_TOKEN", raising=False)
    client = TestClient(app, base_url="http://localhost")
    response = client.post("/mcp/", json={"jsonrpc":"2.0","id":1,"method":"tools/list"}, headers={"Accept":"application/json, text/event-stream"})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_mcp_denied_with_invalid_secret(monkeypatch):
    monkeypatch.setenv("NEXUS_MCP_INTERNAL_TOKEN", "x"*48)
    client = TestClient(app, base_url="http://localhost")
    response = client.post("/mcp/", json={"jsonrpc":"2.0","id":1,"method":"tools/list"}, headers={"Authorization":"Bearer wrong"})
    assert response.status_code == 401
