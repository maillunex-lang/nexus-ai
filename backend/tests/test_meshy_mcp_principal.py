from unittest.mock import patch
import pytest
from nexus.mcp_principal import principal_var, require_owner, resolve
from nexus.mcp_server import nexus_meshy_request_status

def test_no_principal_denied():
    token = principal_var.set(None)
    try:
        with pytest.raises(PermissionError):
            require_owner()
    finally:
        principal_var.reset(token)

def test_viewer_denied():
    token = principal_var.set({"user_id":"u","scope":"mcp:read","roles":["viewer"]})
    try:
        with pytest.raises(PermissionError):
            require_owner()
    finally:
        principal_var.reset(token)

def test_owner_read_allowed():
    value={"user_id":"u","scope":"mcp:read","roles":["owner"]}
    token=principal_var.set(value)
    try:
        assert require_owner()==value
        assert nexus_meshy_request_status("invalid")["error"]=="invalid_request_id"
    finally:
        principal_var.reset(token)

def test_resolve_rejects_missing_bearer():
    assert resolve("Basic xyz") is None

def test_resolve_user():
    with patch("nexus.mcp_principal.oauth_token_principal",return_value={"user_id":"u","scope":"mcp:read","roles":["owner"]}) as fn:
        assert resolve("Bearer abc")["user_id"]=="u"
        fn.assert_called_once_with("abc")
