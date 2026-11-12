from unittest.mock import patch
from fastapi import HTTPException
import pytest
from nexus.oauth_server import consent_preview
from nexus.main import oauth_metadata,oauth_resource_metadata

def test_owner_can_preview_write_but_not_auto_authorize():
 with patch("nexus.oauth_server.current_user",return_value={"id":"owner","username":"owner","roles":["owner"]}),patch("nexus.oauth_server.connection") as connection:
  connection.return_value.__enter__.return_value.execute.return_value.fetchone.return_value=("ChatGPT",["https://example.org/callback"])
  p=consent_preview("chatgpt","https://example.org/callback",None,"mcp:write")
  assert p["scope"]=="mcp:write" and p["consent_required"] is True

def test_non_owner_cannot_preview_write():
 with patch("nexus.oauth_server.current_user",return_value={"id":"viewer","username":"viewer","roles":["viewer"]}):
  with pytest.raises(HTTPException) as exc:
   consent_preview("chatgpt","https://example.org/callback",None,"mcp:write")
  assert exc.value.status_code==403

def test_unknown_scope_rejected():
 with patch("nexus.oauth_server.current_user",return_value={"id":"owner","username":"owner","roles":["owner"]}):
  with pytest.raises(HTTPException) as exc:
   consent_preview("chatgpt","https://example.org/callback",None,"admin")
  assert exc.value.status_code==400

def test_discovery_advertises_write_without_grant(monkeypatch):
 monkeypatch.setenv("NEXUS_OAUTH_ISSUER","https://example.org")
 assert "mcp:write" in oauth_metadata()["scopes_supported"]
 assert "mcp:write" in oauth_resource_metadata()["scopes_supported"]
