import json
from unittest.mock import patch
from nexus import godot_build_queue as q
from nexus.mcp_principal import principal_var

JOB="godot-"+"a"*32

def test_owner_validated_submission_and_status(tmp_path):
    token=principal_var.set({"user_id":"owner-1","roles":["owner"],"scope":"mcp:write"})
    try:
        with patch.object(q,"QUEUE",tmp_path),patch.object(q,"validation_status",return_value={"state":"completed","result":{"passed":True,"workspace_job_id":JOB}}):
            result=q.submit(JOB)
            assert result["state"]=="queued"
            assert q.status(result["job_id"])["state"]=="pending"
            other=principal_var.set({"user_id":"other","roles":["owner"],"scope":"mcp:read"})
            try:
                assert q.status(result["job_id"])["error"]=="not_found"
            finally:
                principal_var.reset(other)
    finally:
        principal_var.reset(token)

def test_reject_unvalidated_job(tmp_path):
    token=principal_var.set({"user_id":"owner-1","roles":["owner"],"scope":"mcp:write"})
    try:
        with patch.object(q,"QUEUE",tmp_path),patch.object(q,"validation_status",return_value={"error":"not_found"}):
            assert q.submit(JOB)["error"]=="validated_owned_job_required"
    finally:
        principal_var.reset(token)

def test_read_scope_cannot_build():
    token=principal_var.set({"user_id":"owner-1","roles":["owner"],"scope":"mcp:read"})
    try:
        try:
            q.submit(JOB)
        except PermissionError:
            pass
        else:
            assert False
    finally:
        principal_var.reset(token)
