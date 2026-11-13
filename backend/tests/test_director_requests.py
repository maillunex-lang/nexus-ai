from unittest.mock import patch
from fastapi import HTTPException
import pytest
from nexus import director_requests as d
from nexus.mcp_principal import principal_var

def test_read_scope_creates_only_pending_request(tmp_path):
 token=principal_var.set({"user_id":"owner1","roles":["owner"],"scope":"mcp:read"})
 try:
  with patch.object(d,"ROOT",tmp_path),patch.object(d,"_entries",return_value={"future-game":{"name":"Future","inspection_only":True},"watermmo":{"name":"WaterMMO"}}):
   r=d.propose("future-game","inspect_project","Audit graphics")
   assert r["status"]=="pending" and r["executed"] is False
   assert r["approval_url"].startswith("https://rikagro.ru/nexusai/?approval=req-")
   assert d.status(r["request_id"])["action"]=="inspect_project"
   assert d.propose("future-game","build_android_debug")["error"]=="project_not_build_enabled"
   assert d.propose("watermmo","shell_command")["error"]=="unsupported_action"
 finally:principal_var.reset(token)

def test_only_owner_can_review_and_no_duplicate_execution(tmp_path):
 token=principal_var.set({"user_id":"owner1","roles":["owner"],"scope":"mcp:read"})
 try:
  with patch.object(d,"ROOT",tmp_path),patch.object(d,"_entries",return_value={"watermmo":{"name":"WaterMMO"}}):
   r=d.propose("watermmo","build_android_debug")
   with patch.object(d,"current_user",return_value={"id":"viewer","roles":["viewer"]}):
    with pytest.raises(HTTPException) as err:d.review(r["request_id"],"approved",None)
    assert err.value.status_code==403
   with patch.object(d,"current_user",return_value={"id":"owner1","roles":["owner"]}),patch.object(d,"build_start",return_value={"job_id":"godot-123","state":"queued"}) as start:
    result=d.review(r["request_id"],"approved",None)
    assert result["status"]=="queued"
    start.assert_called_once_with("watermmo")
    with pytest.raises(HTTPException) as err:d.review(r["request_id"],"approved",None)
    assert err.value.status_code==409
 finally:principal_var.reset(token)

def test_approved_build_status_and_download(tmp_path):
 token=principal_var.set({"user_id":"owner1","roles":["owner"],"scope":"mcp:read"})
 try:
  with patch.object(d,"ROOT",tmp_path),patch.object(d,"_entries",return_value={"watermmo":{"name":"WaterMMO"}}):
   r=d.propose("watermmo","build_android_debug")
   with patch.object(d,"current_user",return_value={"id":"owner1","roles":["owner"]}),patch.object(d,"build_start",return_value={"job_id":"godot-"+"a"*32,"state":"queued"}):
    d.review(r["request_id"],"approved",None)
    with patch.object(d,"build_status",return_value={"state":"completed","result":{"passed":True}}):
     assert d.get(r["request_id"],None)["build"]["state"]=="completed"
     assert d.status(r["request_id"])["build"]["result"]["passed"]
    with patch.object(d,"apk_issue",return_value={"download_url":"/nexusai/private-link"}) as issue:
     assert d.download_link(r["request_id"],None)["download_url"].startswith("/nexusai/")
     issue.assert_called_once_with("godot-"+"a"*32)
 finally:principal_var.reset(token)
