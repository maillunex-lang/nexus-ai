import pytest
from unittest.mock import patch
from nexus.mcp_principal import principal_var
from nexus.mcp_server import nexus_meshy_prepare_request

def test_prepare_requires_oauth_owner():
    token=principal_var.set(None)
    try:
        with pytest.raises(PermissionError):
            nexus_meshy_prepare_request("A realistic farm tractor")
    finally:
        principal_var.reset(token)

def test_prepare_rejects_credit_ceiling_without_database():
    token=principal_var.set({"user_id":"user","scope":"mcp:read","roles":["owner"]})
    try:
        assert nexus_meshy_prepare_request("A realistic farm tractor",max_credits=0)["error"]=="invalid_credit_ceiling"
        assert nexus_meshy_prepare_request("A realistic farm tractor",max_credits=True)["error"]=="invalid_credit_ceiling"
        assert nexus_meshy_prepare_request("short")["error"]=="prompt_length_invalid"
    finally:
        principal_var.reset(token)

def test_prepare_rejects_viewer():
    token=principal_var.set({"user_id":"user","scope":"mcp:read","roles":["viewer"]})
    try:
        with pytest.raises(PermissionError):
            nexus_meshy_prepare_request("A realistic farm tractor")
    finally:
        principal_var.reset(token)
