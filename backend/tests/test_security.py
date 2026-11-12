from fastapi.testclient import TestClient
from nexus.main import app


def test_mcp_denied_without_secret(monkeypatch):
    monkeypatch.delenv("NEXUS_MCP_INTERNAL_TOKEN", raising=False)
    with TestClient(app, base_url="http://localhost") as client:
        response = client.post("/mcp/", json={"jsonrpc":"2.0","id":1,"method":"tools/list"}, headers={"Accept":"application/json, text/event-stream"})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_mcp_denied_with_invalid_secret(monkeypatch):
    monkeypatch.setenv("NEXUS_MCP_INTERNAL_TOKEN", "x"*48)
    with TestClient(app, base_url="http://localhost") as client:
        response = client.post("/mcp/", json={"jsonrpc":"2.0","id":1,"method":"tools/list"}, headers={"Authorization":"Bearer wrong"})
    assert response.status_code == 401
