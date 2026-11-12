from unittest.mock import patch
from fastapi import HTTPException
import pytest
from nexus.mcp_principal import principal_var, require_owner, require_owner_write
from nexus.mcp_server import nexus_meshy_review_request
from nexus.oauth_server import AuthorizeRequest, authorize

def test_read_scope_cannot_approve():
    token=principal_var.set({"user_id":"u","roles":["owner"],"scope":"mcp:read"})
    try:
        with pytest.raises(PermissionError):
            require_owner_write()
    finally:
        principal_var.reset(token)

def test_owner_write_can_review_validation():
    token=principal_var.set({"user_id":"u","roles":["owner"],"scope":"mcp:write"})
    try:
        assert require_owner()["scope"]=="mcp:write"
        assert nexus_meshy_review_request("invalid","approve")["error"]=="invalid_request_id"
        assert nexus_meshy_review_request("invalid","dispatch")["error"]=="invalid_decision"
    finally:
        principal_var.reset(token)

def test_viewer_write_denied():
    token=principal_var.set({"user_id":"u","roles":["viewer"],"scope":"mcp:write"})
    try:
        with pytest.raises(PermissionError):
            require_owner_write()
    finally:
        principal_var.reset(token)
