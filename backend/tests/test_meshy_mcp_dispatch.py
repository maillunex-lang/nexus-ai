from unittest.mock import patch
from uuid import UUID
import pytest
from nexus.mcp_principal import principal_var
from nexus.mcp_server import nexus_meshy_dispatch_preview,nexus_meshy_dispatch_refine,nexus_meshy_refine_status

RID="00000000-0000-0000-0000-000000000001"

@pytest.mark.parametrize("tool", [nexus_meshy_dispatch_preview,nexus_meshy_dispatch_refine])
def test_read_scope_cannot_dispatch(tool):
    token=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:read"})
    try:
        with patch("nexus.meshy_dispatch.dispatch") as preview,patch("nexus.meshy_refine_dispatch.dispatch") as refine:
            with pytest.raises(PermissionError):
                tool(RID,"DISPATCH "+RID)
            preview.assert_not_called()
            refine.assert_not_called()
    finally:
        principal_var.reset(token)

@pytest.mark.parametrize("tool", [nexus_meshy_dispatch_preview,nexus_meshy_dispatch_refine])
def test_wrong_confirmation_never_dispatches(tool):
    token=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:write"})
    try:
        with patch("nexus.meshy_dispatch.dispatch") as preview,patch("nexus.meshy_refine_dispatch.dispatch") as refine:
            assert tool(RID,"yes")["error"]=="explicit_dispatch_confirmation_required"
            preview.assert_not_called()
            refine.assert_not_called()
    finally:
        principal_var.reset(token)

@pytest.mark.parametrize("tool,module", [(nexus_meshy_dispatch_preview,"nexus.meshy_dispatch.dispatch"),(nexus_meshy_dispatch_refine,"nexus.meshy_refine_dispatch.dispatch")])
def test_explicit_confirmation_passes_verified_identity(tool,module):
    token=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:write"})
    try:
        with patch(module,return_value={"status":"submitted"}) as dispatch:
            assert tool(RID,"DISPATCH "+RID)=={"status":"submitted"}
            dispatch.assert_called_once_with(UUID(RID),None,owner_id="owner")
    finally:
        principal_var.reset(token)

def test_status_requires_owner():
    token=principal_var.set({"user_id":"viewer","roles":["viewer"],"scope":"mcp:read"})
    try:
        with pytest.raises(PermissionError):
            nexus_meshy_refine_status(RID)
    finally:
        principal_var.reset(token)
