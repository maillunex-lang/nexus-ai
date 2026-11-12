from unittest.mock import patch
from nexus import autonomous_director as d
from nexus.mcp_principal import principal_var

def test_owner_can_queue_deterministic_workflow():
    token=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:write"})
    try:
        with patch.object(d,"queue_build",return_value={"job_id":"godot-"+"a"*32,"state":"queued"}):
            result=d.run("basheco")
            assert result["state"]=="queued" and not result["published"]
            assert result["next_tool"]=="nexus_director_status"
        assert d.run("basheco","invent_game")["error"]=="unsupported_workflow"
        assert d.run("unregistered")["error"]=="project_not_build_enabled"
    finally:principal_var.reset(token)

def test_read_scope_cannot_run():
    token=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:read"})
    try:
        try:d.run("basheco")
        except PermissionError:pass
        else:assert False
    finally:principal_var.reset(token)

def test_status_is_owned_and_bounded():
    token=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:read"})
    try:
        assert d.check("../secret")["error"]=="invalid_job_id"
        with patch.object(d,"build_status",return_value={"state":"completed","result":{"passed":True,"sha256":"b"*64,"bytes":123}}):
            result=d.check("godot-"+"a"*32)
            assert result["passed"] and result["next_tool"]=="nexus_godot_apk_download_link"
        with patch.object(d,"build_status",return_value={"state":"failed","result":{"passed":False,"error":"godot_validation_failed"}}):
            assert d.check("godot-"+"a"*32)["next_action"]=="inspect_error_and_request_explicit_fix"
    finally:principal_var.reset(token)

def test_anonymous_denied():
    try:d.capabilities()
    except PermissionError:pass
    else:assert False
