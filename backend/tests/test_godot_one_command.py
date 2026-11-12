import json
from unittest.mock import patch
from nexus import godot_one_command as one
from nexus import godot_projects as projects
from nexus.mcp_principal import principal_var

def test_one_command_owner_write_queues_no_change(tmp_path):
    root=tmp_path/"game"
    root.mkdir()
    (root/"project.godot").write_text("[application]\n")
    token=principal_var.set({"user_id":"owner-1","roles":["owner"],"scope":"mcp:write"})
    try:
        with patch.object(one,"QUEUE",tmp_path/"queue"),patch.dict(projects.PROJECTS,{"basheco":{"name":"BASHECO","root":str(root)}}):
            result=one.start("basheco")
            assert result["state"]=="queued"
            assert result["source_modified"] is False
            file=tmp_path/"queue"/"build_pending"/(result["job_id"]+".json")
            payload=json.loads(file.read_text())
            assert payload["kind"]=="auto_android_debug_build"
            assert payload["requested_by"]=="owner-1"
            assert (root/"project.godot").read_text()=="[application]\n"
    finally:
        principal_var.reset(token)

def test_invalid_project_fails_closed():
    token=principal_var.set({"user_id":"owner-1","roles":["owner"],"scope":"mcp:write"})
    try:
        assert one.start("../../other")["error"]=="unknown_or_unconfigured_project"
    finally:
        principal_var.reset(token)

def test_read_only_token_cannot_queue():
    token=principal_var.set({"user_id":"owner-1","roles":["owner"],"scope":"mcp:read"})
    try:
        try:
            one.start("basheco")
        except PermissionError:
            pass
        else:
            assert False
    finally:
        principal_var.reset(token)
