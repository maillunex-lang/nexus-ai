from unittest.mock import patch
from nexus import godot_project_onboarding as o
from nexus.mcp_principal import principal_var

def test_owner_creates_template_job(tmp_path):
    t=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:write"})
    try:
        with patch.object(o,"QUEUE",tmp_path):
            r=o.request("new-game","template","My New Game")
            assert r["state"]=="queued" and r["build_enabled"] is False
            assert o.status(r["job_id"])["state"]=="pending"
            assert o.request("new-game","template",'bad"\\name')["error"]=="invalid_project_title"
    finally:principal_var.reset(t)

def test_read_only_cannot_create():
    t=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:read"})
    try:
        try:o.request("new-game","template","Game")
        except PermissionError:pass
        else:assert False
    finally:principal_var.reset(t)
