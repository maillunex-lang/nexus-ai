from unittest.mock import patch
from nexus import director_workflows as d
from nexus.mcp_principal import principal_var

def _owner(scope="mcp:write"):
 return principal_var.set({"user_id":"director-owner","roles":["owner"],"scope":scope})

def test_inspect_and_owner_journal(tmp_path):
 t=_owner()
 try:
  with patch.object(d,"BASE",tmp_path),patch.object(d,"inspect_project",return_value={"file_count":3}):
   r=d.launch("inspect_project","basheco")
   assert r["state"]=="completed"
   assert d.inspect(r["director_job_id"])["passed"]
   assert len(d.journal(r["director_job_id"])["events"])>=2
 finally:d.principal_var.reset(t) if hasattr(d,"principal_var") else __import__("nexus.mcp_principal",fromlist=["principal_var"]).principal_var.reset(t)

def test_build_transitions_and_error_policy(tmp_path):
 t=_owner()
 try:
  with patch.object(d,"BASE",tmp_path),patch.object(d,"build_start",return_value={"state":"queued","job_id":"godot-"+"a"*32}):
   r=d.launch("validate_and_build_android","basheco")
   job=r["director_job_id"]
   with patch.object(d,"build_status",return_value={"state":"running"}):
    assert d.inspect(job)["step"]=="godot_validation"
   with patch.object(d,"build_status",return_value={"state":"failed","result":{"error":"godot_validation_failed"}}):
    assert d.inspect(job)["policy"]=="stop_and_report"
    assert d.inspect(job)["auto_retry"] is False
    assert len(d.journal(job)["events"])==3
 finally:__import__("nexus.mcp_principal",fromlist=["principal_var"]).principal_var.reset(t)

def test_multiple_types_and_access(tmp_path):
 t=_owner()
 try:
  with patch.object(d,"BASE",tmp_path),patch.object(d,"register_start",return_value={"state":"queued","job_id":"onboard-"+"a"*32}):
   for workflow in ("register_github","register_lunex","create_godot_project"):
    assert d.launch(workflow,"new-game","source")["state"]=="queued"
   assert d.launch("arbitrary_shell","new-game")["error"]=="unsupported_workflow"
 finally:__import__("nexus.mcp_principal",fromlist=["principal_var"]).principal_var.reset(t)
 t=_owner("mcp:read")
 try:
  assert d.inspect("director-"+"a"*32)["error"]=="not_found"
  try:d.launch("inspect_project","basheco")
  except PermissionError:pass
  else:assert False
 finally:__import__("nexus.mcp_principal",fromlist=["principal_var"]).principal_var.reset(t)
