from fastapi.testclient import TestClient
from nexus.main import app
from nexus.oauth_server import AuthorizeRequest, TokenRequest
from pydantic import ValidationError
import pytest


def test_authorize_needs_login():
    client=TestClient(app,base_url="http://localhost")
    payload={"client_id":"unknown","redirect_uri":"https://example.org/callback","response_type":"code","code_challenge":"a"*43,"code_challenge_method":"S256","state":"state123456"}
    assert client.post("/oauth/authorize",json=payload).status_code==401


def test_token_bad_grant():
    client=TestClient(app,base_url="http://localhost")
    assert client.post("/oauth/token",data={"grant_type":"password","code":"x","client_id":"x","redirect_uri":"https://example.org/callback","code_verifier":"a"*43}).status_code==400


def test_token_empty_code_rejected():
    client=TestClient(app,base_url="http://localhost")
    assert client.post("/oauth/token",data={"grant_type":"authorization_code","code":"","client_id":"unknown","redirect_uri":"https://example.org/callback","code_verifier":"a"*43}).status_code==400


def test_revoke_requires_login():
    client=TestClient(app,base_url="http://localhost")
    assert client.post("/oauth/revoke",json={"client_id":"unknown"}).status_code==401


def test_consent_preview_requires_login():
    client=TestClient(app,base_url="http://localhost")
    assert client.get("/oauth/consent",params={"client_id":"unknown","redirect_uri":"https://example.org/callback"}).status_code==401


def test_authorize_requires_explicit_consent_even_with_session(monkeypatch):
    from nexus.identity import current_user
    app.dependency_overrides[current_user] = lambda: {"id":"test","username":"owner","roles":["owner"]}
    # OAuth authorize calls current_user directly, not via dependency injection.
    monkeypatch.setattr("nexus.oauth_server.current_user", lambda request: {"id":"test","username":"owner","roles":["owner"]})
    try:
        client=TestClient(app,base_url="http://localhost")
        payload={"client_id":"unknown","redirect_uri":"https://example.org/callback","response_type":"code","code_challenge":"a"*43,"code_challenge_method":"S256","state":"state123456"}
        assert client.post("/oauth/authorize",json=payload).status_code==400
    finally:
        app.dependency_overrides.clear()


def test_token_rejects_json():
    client=TestClient(app,base_url="http://localhost")
    assert client.post("/oauth/token",json={"grant_type":"authorization_code"}).status_code==415


def test_token_rejects_duplicate_form_fields():
    client=TestClient(app,base_url="http://localhost")
    assert client.post("/oauth/token",content="grant_type=authorization_code&grant_type=password",headers={"content-type":"application/x-www-form-urlencoded"}).status_code==400


def test_discovery_disabled_without_issuer(monkeypatch):
    monkeypatch.delenv("NEXUS_OAUTH_ISSUER",raising=False)
    client=TestClient(app,base_url="http://localhost")
    assert client.get("/.well-known/oauth-authorization-server").status_code==404
    assert client.get("/.well-known/oauth-protected-resource").status_code==404


def test_discovery_issuer_metadata(monkeypatch):
    monkeypatch.setenv("NEXUS_OAUTH_ISSUER","https://nexus.example.org")
    client=TestClient(app,base_url="http://localhost")
    response=client.get("/.well-known/oauth-authorization-server")
    assert response.status_code==200
    assert response.json()["code_challenge_methods_supported"]==["S256"]
    assert response.json()["token_endpoint"]=="https://nexus.example.org/oauth/token"


def test_browser_authorize_get_redirects_to_consent_spa():
    client=TestClient(app,base_url="http://localhost",follow_redirects=False)
    response=client.get("/oauth/authorize?client_id=sample&state=state123456")
    assert response.status_code==303
    assert response.headers["location"].startswith("/nexusai/?oauth=1&")
    assert "client_id=sample" in response.headers["location"]
