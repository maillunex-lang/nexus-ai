from unittest.mock import patch
from fastapi import HTTPException
from nexus.mcp_principal import principal_var
from nexus.mcp_server import nexus_meshy_review_refine, nexus_meshy_dispatch_readiness
from nexus.meshy_dispatch import dispatch
import pytest
from uuid import UUID

RID="00000000-0000-0000-0000-000000000001"

def test_paid_dispatch_disabled_by_default_before_network():
    with patch.dict("os.environ",{},clear=True), patch("nexus.meshy_dispatch.owner",return_value={"id":"owner"}), patch("nexus.meshy_dispatch.balance") as balance:
        with pytest.raises(HTTPException) as err:
            dispatch(UUID(RID),None)
        assert err.value.status_code==503
        balance.assert_not_called()

def test_refine_review_requires_write_scope():
    token=principal_var.set({"user_id":"u","scope":"mcp:read","roles":["owner"]})
    try:
        with pytest.raises(PermissionError):
            nexus_meshy_review_refine(RID,"approve")
    finally:
        principal_var.reset(token)

def test_refine_review_invalid_decision():
    token=principal_var.set({"user_id":"u","scope":"mcp:write","roles":["owner"]})
    try:
        assert nexus_meshy_review_refine(RID,"dispatch")["error"]=="invalid_decision"
    finally:
        principal_var.reset(token)

def test_dispatch_readiness_rejects_invalid_id():
    token=principal_var.set({"user_id":"u","scope":"mcp:read","roles":["owner"]})
    try:
        assert nexus_meshy_dispatch_readiness("invalid")["error"]=="invalid_request_id"
    finally:
        principal_var.reset(token)
