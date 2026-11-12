import hashlib
import json
import time
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from nexus import godot_apk_delivery as delivery
from nexus.mcp_principal import principal_var

JOB="godot-"+"a"*32
WORKSPACE="godot-"+"b"*32

def fixture_build(tmp_path):
    queue=tmp_path/"queue"
    folder=tmp_path/"workspaces"/WORKSPACE
    (queue/"build_completed").mkdir(parents=True)
    (folder/"nexus-build").mkdir(parents=True)
    apk=folder/"nexus-build/android-debug.apk"
    apk.write_bytes(b"test apk bytes")
    sha=hashlib.sha256(apk.read_bytes()).hexdigest()
    result={"passed":True,"sha256":sha,"bytes":apk.stat().st_size,"workspace_job_id":WORKSPACE}
    (queue/"build_completed"/(JOB+".json")).write_text(json.dumps({"job_id":JOB,"requested_by":"owner-1","result":result}))
    return queue,folder.parent.parent,sha,result

def test_owner_issues_link_and_download_verifies_hash(tmp_path):
    queue,root,sha,result=fixture_build(tmp_path)
    principal=principal_var.set({"user_id":"owner-1","roles":["owner"],"scope":"mcp:read"})
    try:
        with patch.object(delivery,"QUEUE",queue),patch.object(delivery,"WORKSPACES",root),patch.object(delivery,"status",return_value={"state":"completed","result":result}),patch.dict("os.environ",{"NEXUS_MCP_INTERNAL_TOKEN":"x"*48}):
            issued=delivery.issue(JOB)
            assert issued["ttl_seconds"]==300
            from urllib.parse import urlsplit,parse_qs
            qs=parse_qs(urlsplit(issued["download_url"]).query)
            response=delivery.download(JOB,int(qs["expires"][0]),qs["sha256"][0],qs["signature"][0])
            assert response.status_code==200
            assert response.headers["cache-control"].startswith("private")
            with pytest.raises(HTTPException):
                delivery.download(JOB,int(qs["expires"][0]),qs["sha256"][0],"0"*64)
            with pytest.raises(HTTPException):
                delivery.download(JOB,int(time.time())-1,sha,qs["signature"][0])
    finally:
        principal_var.reset(principal)

def test_link_cannot_be_issued_for_unowned_build():
    principal=principal_var.set({"user_id":"owner-2","roles":["owner"],"scope":"mcp:read"})
    try:
        with patch.object(delivery,"status",return_value={"error":"not_found"}):
            assert delivery.issue(JOB)["error"]=="completed_owned_build_required"
    finally:
        principal_var.reset(principal)

def test_unauthenticated_link_issue_rejected():
    with pytest.raises(PermissionError):
        delivery.issue(JOB)
