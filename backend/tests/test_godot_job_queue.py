import hashlib
from unittest.mock import patch
from nexus import godot_job_queue as queue
from nexus import godot_projects as gp
from nexus.mcp_principal import principal_var

def test_queue_and_owner_scoped_status(tmp_path):
    source=tmp_path/"source"
    source.mkdir()
    (source/"project.godot").write_text("[application]\n")
    old="extends Node\n"
    (source/"main.gd").write_text(old)
    token=principal_var.set({"user_id":"owner-1","roles":["owner"],"scope":"mcp:write"})
    try:
        with patch.object(queue,"QUEUE",tmp_path/"queue"),patch.dict(gp.PROJECTS,{"basheco":{"name":"Test","root":str(source)}}):
            sha=hashlib.sha256(old.encode()).hexdigest()
            result=queue.submit("basheco","main.gd",sha,"extends Node\n# test\n")
            assert result["state"]=="queued"
            assert queue.status(result["job_id"])["state"]=="pending"
            assert (source/"main.gd").read_text()==old
            other=principal_var.set({"user_id":"owner-2","roles":["owner"],"scope":"mcp:read"})
            try:
                assert queue.status(result["job_id"])["error"]=="not_found"
            finally:
                principal_var.reset(other)
    finally:
        principal_var.reset(token)

def test_read_only_scope_rejects_queue(tmp_path):
    token=principal_var.set({"user_id":"owner-1","roles":["owner"],"scope":"mcp:read"})
    try:
        try:
            queue.submit("basheco","main.gd","0"*64,"new")
        except PermissionError:
            pass
        else:
            assert False,"read-only token must not submit jobs"
    finally:
        principal_var.reset(token)
