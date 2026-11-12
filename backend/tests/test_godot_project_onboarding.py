from unittest.mock import patch
from nexus import godot_project_onboarding as o
from nexus.mcp_principal import principal_var

def test_github_registration_is_queued_without_build_permission(tmp_path):
    t=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:write"})
    try:
        with patch.object(o,"QUEUE",tmp_path):
            r=o.request("my-game","github","example/mygame")
            assert r["state"]=="queued" and r["build_enabled"] is False
            assert o.status(r["job_id"])["state"]=="pending"
    finally:principal_var.reset(t)

def test_lunex_path_is_restricted(tmp_path):
    t=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:write"})
    try:
        with patch.object(o,"QUEUE",tmp_path):
            assert o.request("my-game","lunex","/etc")["error"]=="invalid_lunex_path"
            assert o.request("my-game","lunex","/opt/nexus-ai/secrets")["error"]=="reserved_path"
            assert o.request("my-game","lunex","/opt/../etc")["error"]=="invalid_lunex_path"
    finally:principal_var.reset(t)

def test_owner_required():
    try:o.request("my-game","github","example/mygame")
    except PermissionError:pass
    else:assert False
