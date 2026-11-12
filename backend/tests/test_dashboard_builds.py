from unittest.mock import patch
from fastapi import HTTPException
import pytest
from nexus import dashboard_builds as db

def test_owner_can_enqueue_via_session_without_oauth_scope():
 with patch.object(db,"current_user",return_value={"id":"owner1","roles":["owner"]}),patch.object(db,"start",return_value={"job_id":"godot-123","state":"queued"}) as start:
  result=db.enqueue(None,"watermmo")
  assert result["state"]=="queued"
  start.assert_called_once_with("watermmo")

def test_non_owner_cannot_build():
 with patch.object(db,"current_user",return_value={"id":"viewer","roles":["viewer"]}):
  with pytest.raises(HTTPException) as err:db.enqueue(None,"watermmo")
  assert err.value.status_code==403

def test_unknown_project_rejected():
 with pytest.raises(HTTPException) as err:db.enqueue(None,"../../bad")
 assert err.value.status_code==404

def test_status_and_download_require_owner():
 with patch.object(db,"current_user",return_value={"id":"owner1","roles":["owner"]}),patch.object(db,"status",return_value={"state":"completed"}) as status,patch.object(db,"issue",return_value={"download_url":"/test"}) as issue:
  assert db.check(None,"godot-test")["state"]=="completed"
  assert db.link(None,"godot-test")["download_url"]=="/test"
  status.assert_called_once_with("godot-test")
  issue.assert_called_once_with("godot-test")
