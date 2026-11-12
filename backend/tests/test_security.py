from fastapi.testclient import TestClient
from nexus.main import app


def test_mcp_denied_without_secret(monkeypatch):
    monkeypatch.delenv("NEXUS_MCP_INTERNAL_TOKEN", raising=False)
    client = TestClient(app, base_url="http://localhost")
    response = client.post("/mcp/", json={"jsonrpc":"2.0","id":1,"method":"tools/list"}, headers={"Accept":"application/json, text/event-stream"})
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_mcp_denied_with_invalid_secret(monkeypatch):
    monkeypatch.setattr("nexus.security.oauth_token_identity", lambda token: False)
    monkeypatch.setenv("NEXUS_MCP_INTERNAL_TOKEN", "x"*48)
    client = TestClient(app, base_url="http://localhost")
    response = client.post("/mcp/", json={"jsonrpc":"2.0","id":1,"method":"tools/list"}, headers={"Authorization":"Bearer wrong"})
    assert response.status_code == 401


def test_internal_token_disabled_for_public_issuer(monkeypatch):
    from nexus.security import authorized_bearer
    monkeypatch.setenv("NEXUS_OAUTH_ISSUER", "https://nexus.example.org")
    monkeypatch.setenv("NEXUS_MCP_INTERNAL_TOKEN", "x"*48)
    monkeypatch.setattr("nexus.security.oauth_token_identity", lambda token: False)
    assert not authorized_bearer("Bearer " + "x"*48)


def test_database_error_fails_closed(monkeypatch):
    from nexus.security import authorized_bearer
    monkeypatch.setenv("NEXUS_OAUTH_ISSUER", "https://nexus.example.org")
    def unavailable(token):
        raise ConnectionError("database unavailable")
    monkeypatch.setattr("nexus.security.oauth_token_identity", unavailable)
    assert not authorized_bearer("Bearer testtoken")


def test_cross_site_auth_write_rejected():
    client = TestClient(app, base_url="http://localhost")
    response = client.post("/oauth/authorize", headers={"Sec-Fetch-Site": "cross-site"}, json={})
    assert response.status_code == 403


def test_mcp_challenge_metadata_when_issuer_configured(monkeypatch):
    monkeypatch.setenv("NEXUS_OAUTH_ISSUER", "https://nexus.example.org")
    monkeypatch.setattr("nexus.security.oauth_token_identity", lambda token: False)
    client = TestClient(app, base_url="http://localhost")
    response = client.post("/mcp/", headers={"Authorization":"Bearer invalid"})
    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]
