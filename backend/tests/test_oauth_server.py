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
    assert client.post("/oauth/token",json={"grant_type":"password","code":"x","client_id":"x","redirect_uri":"https://example.org/callback","code_verifier":"a"*43}).status_code==400


def test_token_empty_code_rejected():
    client=TestClient(app,base_url="http://localhost")
    assert client.post("/oauth/token",json={"grant_type":"authorization_code","code":"","client_id":"unknown","redirect_uri":"https://example.org/callback","code_verifier":"a"*43}).status_code==400


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
