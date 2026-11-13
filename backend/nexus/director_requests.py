"""Owner-reviewed MCP requests. Read-scoped tokens may propose, never execute.

Requests are immutable JSON records in the existing shared queue. Review is
restricted to an authenticated owner browser session. Only allowlisted
operations can execute; no arbitrary source edits, shell or publishing.
"""
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import HTTPException, Request
from .godot_job_queue import QUEUE
from .godot_projects import _entries
from .identity import current_user
from .mcp_principal import require_owner, principal_var
from .godot_one_command import start as build_start
from .godot_build_queue import status as build_status
from .godot_apk_delivery import issue as apk_issue
from .godot_projects import inspect_project
from . import director_pipelines as pipelines
from . import director_changesets as changesets

ROOT=QUEUE/"director-requests"
ID=re.compile(r"req-[0-9a-f]{32}\Z")
PROJECT=re.compile(r"[a-z][a-z0-9-]{2,39}\Z")
ACTIONS={"inspect_project","build_android_debug"}
BASE_URL="https://rikagro.ru/nexusai/?approval="
def _path(request_id):
 if not isinstance(request_id,str) or not ID.fullmatch(request_id):
  raise HTTPException(404,"Request not found")
 return ROOT/(request_id+".json")
def _read(request_id):
 path=_path(request_id)
 if path.is_symlink() or not path.is_file() or path.stat().st_size>12000:
  raise HTTPException(404,"Request not found")
 return json.loads(path.read_text())
def _save(data,exclusive=False):
 ROOT.mkdir(parents=True,exist_ok=True)
 path=_path(data["id"])
 if exclusive:
  fd=os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,"w") as f:json.dump(data,f,ensure_ascii=False)
 else:
  tmp=ROOT/("."+data["id"]+"-"+uuid.uuid4().hex+".tmp")
  fd=os.open(str(tmp),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,"w") as f:json.dump(data,f,ensure_ascii=False)
  os.replace(tmp,path)
def propose(project_id:str,action:str,description:str="")->dict:
 owner=require_owner()  # mcp:read is sufficient ONLY to create an inert request
 if not isinstance(project_id,str) or not PROJECT.fullmatch(project_id) or project_id not in _entries():
  return {"error":"unknown_project"}
 if action not in ACTIONS:return {"error":"unsupported_action","actions":sorted(ACTIONS)}
 if not isinstance(description,str) or len(description)>1500 or any(ord(c)<32 and c not in "\n\t" for c in description):
  return {"error":"invalid_description"}
 if action=="build_android_debug" and _entries()[project_id].get("inspection_only"):
  return {"error":"project_not_build_enabled","note":"Future projects must first pass explicit build registration."}
 now=datetime.now(timezone.utc)
 data={"id":"req-"+uuid.uuid4().hex,"owner":str(owner["user_id"]),
       "project_id":project_id,"action":action,"description":description,
       "status":"pending","created_at":now.isoformat(),
       "expires_at":(now+timedelta(hours=24)).isoformat(),"result":None}
 _save(data,True)
 return {"request_id":data["id"],"status":"pending","project_id":project_id,
         "action":action,"approval_url":BASE_URL+data["id"],
         "expires_at":data["expires_at"],"executed":False,
         "message":"Отправьте владельцу ссылку approval_url для подтверждения в панели NEXUS."}
def propose_pipeline(pipeline:str,project_id:str,changeset_id:str="",description:str="",task_id:str="")->dict:
 """Inert request to run an exact Director pipeline plan; mcp:read may propose, never execute."""
 owner=require_owner()
 if not isinstance(description,str) or len(description)>1500 or any(ord(c)<32 and c not in "\n\t" for c in description):
  return {"error":"invalid_description"}
 planned=pipelines.plan(pipeline,project_id,changeset_id)
 if planned.get("error"):return planned
 if task_id:
  task=pipelines.task_links.resolve(task_id,str(owner["user_id"]))
  if task.get("error"):return task
  task_id=task["task_id"]
 now=datetime.now(timezone.utc)
 data={"id":"req-"+uuid.uuid4().hex,"owner":str(owner["user_id"]),
       "project_id":project_id,"action":"run_pipeline","description":description,
       "pipeline":pipeline,"changeset_id":changeset_id,"plan_digest":planned["plan_digest"],
       "task_id":task_id,"status":"pending","created_at":now.isoformat(),
       "expires_at":(now+timedelta(hours=24)).isoformat(),"result":None}
 _save(data,True)
 return {"request_id":data["id"],"status":"pending","project_id":project_id,
         "action":"run_pipeline","pipeline":pipeline,"plan_digest":planned["plan_digest"],
         "stages":[stage["name"] for stage in planned["stages"]],
         "approval_url":BASE_URL+data["id"],"expires_at":data["expires_at"],"executed":False,
         "message":"Отправьте владельцу ссылку approval_url для подтверждения в панели NEXUS."}
def propose_adoption(changeset_id:str,description:str="")->dict:
 """Inert request to publish a validated change set as a nexus/ branch and draft PR."""
 from . import director_adoption as adoption
 owner=require_owner()
 if not isinstance(description,str) or len(description)>1500 or any(ord(c)<32 and c not in "\n\t" for c in description):
  return {"error":"invalid_description"}
 planned=adoption.plan(str(owner["user_id"]),changeset_id)
 if planned.get("error"):return planned
 now=datetime.now(timezone.utc)
 data={"id":"req-"+uuid.uuid4().hex,"owner":str(owner["user_id"]),
       "project_id":planned["project_id"],"action":"adopt_changeset","description":description,
       "changeset_id":changeset_id,"plan_digest":planned["adoption_digest"],
       "status":"pending","created_at":now.isoformat(),
       "expires_at":(now+timedelta(hours=24)).isoformat(),"result":None}
 _save(data,True)
 return {"request_id":data["id"],"status":"pending","project_id":planned["project_id"],
         "action":"adopt_changeset","repository":planned["repository"],"base_branch":planned["base_branch"],
         "repository_paths":planned["repository_paths"],"approval_url":BASE_URL+data["id"],
         "expires_at":data["expires_at"],"executed":False,
         "message":"Отправьте владельцу ссылку approval_url. Ветка и черновик pull request создаются только после подтверждения."}
def _with_adoption_state(data):
 """Attach the adoption target and the diff the owner is about to publish."""
 if data.get("status")!="pending":return data
 from . import director_adoption as adoption
 planned=adoption.plan(str(require_owner()["user_id"]),data.get("changeset_id"))
 return {**data,"adoption":planned,"plan_current":planned.get("adoption_digest")==data.get("plan_digest"),
         "changeset":changesets.inspect(data.get("changeset_id"))}
def _with_pipeline_state(data):
 """Attach the reviewed plan, change set diff and live pipeline state for display."""
 extra={}
 if data.get("status")=="pending":
  planned=pipelines.plan(data.get("pipeline"),data.get("project_id"),data.get("changeset_id",""))
  extra["plan"]=planned
  extra["plan_current"]=planned.get("plan_digest")==data.get("plan_digest")
  if data.get("changeset_id"):extra["changeset"]=changesets.inspect(data["changeset_id"])
 elif data.get("status")=="queued":
  identifier=(data.get("result") or {}).get("pipeline_id")
  if isinstance(identifier,str):extra["pipeline_state"]=pipelines.status(identifier)
 return {**data,**extra}
def _with_build_state(data):
 """Read live worker state without modifying an approved request or its audit record."""
 result=data.get("result") or {}
 if data.get("action")=="run_pipeline":return _with_pipeline_state(data)
 if data.get("action")=="adopt_changeset":return _with_adoption_state(data)
 if data.get("action")!="build_android_debug" or data.get("status")!="queued" or not isinstance(result,dict):
  return data
 job=result.get("job_id")
 if not isinstance(job,str):return data
 current=build_status(job)
 return {**data,"build":current}

def status(request_id:str)->dict:
 owner=require_owner()
 data=_read(request_id)
 if data["owner"]!=str(owner["user_id"]):return {"error":"not_found"}
 return _with_build_state({k:data[k] for k in ("id","project_id","action","description","status","created_at","expires_at","result","pipeline","changeset_id","plan_digest","task_id") if k in data})

def download_link(request_id:str,request)->dict:
 user=_session_owner(request)
 data=get(request_id,request)
 if data.get("action")!="build_android_debug" or data.get("status")!="queued":
  return {"error":"approved_build_required"}
 job=(data.get("result") or {}).get("job_id")
 if not isinstance(job,str):return {"error":"build_job_missing"}
 token=principal_var.set({"user_id":str(user["id"]),"roles":["owner"],"scope":"mcp:read"})
 try:return apk_issue(job)
 finally:principal_var.reset(token)
def _session_owner(request):
 user=current_user(request)
 if "owner" not in user["roles"]:raise HTTPException(403,"Owner required")
 return user
def list_pending(request):
 user=_session_owner(request)
 if not ROOT.exists():return {"requests":[]}
 items=[]
 for path in sorted(ROOT.glob("req-*.json"),reverse=True)[:100]:
  if path.is_symlink():continue
  try:
   d=_read(path.stem)
   if d["owner"]==str(user["id"]):items.append(d)
  except (ValueError,OSError,HTTPException,KeyError):continue
 return {"requests":items}
def get(request_id,request):
 user=_session_owner(request)
 d=_read(request_id)
 if d["owner"]!=str(user["id"]):raise HTTPException(404,"Request not found")
 # Live job readers are owner-scoped MCP functions: give them the session owner, read-only.
 token=principal_var.set({"user_id":str(user["id"]),"roles":["owner"],"scope":"mcp:read"})
 try:return _with_build_state(d)
 finally:principal_var.reset(token)
def review(request_id,decision,request):
 user=_session_owner(request)
 if decision not in ("approved","denied"):raise HTTPException(400,"Invalid decision")
 # Atomic single-review lock, protecting against concurrent duplicate execution.
 ROOT.mkdir(parents=True,exist_ok=True)
 lock=ROOT/(request_id+".lock")
 _path(request_id)
 try:fd=os.open(str(lock),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 except FileExistsError:raise HTTPException(409,"Request is being reviewed")
 try:
  os.close(fd)
  d=_read(request_id)
  if d["owner"]!=str(user["id"]):raise HTTPException(404,"Request not found")
  if d["status"]!="pending":raise HTTPException(409,"Already reviewed")
  if datetime.fromisoformat(d["expires_at"])<=datetime.now(timezone.utc):
   d["status"]="expired";_save(d);raise HTTPException(409,"Request expired")
  d["status"]="denied" if decision=="denied" else "approved"
  d["reviewed_by"]=str(user["id"])
  d["reviewed_at"]=datetime.now(timezone.utc).isoformat()
  _save(d)
  if decision=="denied":return d
  token=principal_var.set({"user_id":str(user["id"]),"roles":["owner"],"scope":"mcp:write"})
  try:
   if d["action"]=="build_android_debug":
    if d["project_id"] not in _entries() or _entries()[d["project_id"]].get("inspection_only"):
     result={"error":"project_not_build_enabled"}
    else:result=build_start(d["project_id"])
   elif d["action"]=="run_pipeline":
    # The approved digest pins pipeline, project, change set contents and stage list.
    result=pipelines.launch(d.get("pipeline"),d["project_id"],d.get("changeset_id",""),d.get("plan_digest") or "invalid",d.get("task_id") or "")
    result={k:result.get(k) for k in ("pipeline_id","pipeline","state","current_stage","error") if result.get(k) is not None}
   elif d["action"]=="adopt_changeset":
    from . import director_adoption as adoption
    result=adoption.execute(d.get("changeset_id"),d.get("plan_digest") or "invalid",d.get("description") or "")
   elif d["action"]=="inspect_project":
    result=inspect_project(d["project_id"])
    result={"project_id":d["project_id"],"error":result.get("error"),"file_count":result.get("file_count")}
   else:result={"error":"unsupported_action"}
  except Exception:
   result={"error":"execution_failed"}
  finally:principal_var.reset(token)
  d["result"]=result
  d["status"]="failed" if result.get("error") else "queued" if d["action"] in ("build_android_debug","run_pipeline") else "completed"
  _save(d)
  if d["action"]=="run_pipeline":
   token=principal_var.set({"user_id":str(user["id"]),"roles":["owner"],"scope":"mcp:read"})
   try:return _with_build_state(d)
   finally:principal_var.reset(token)
  return d
 finally:
  lock.unlink(missing_ok=True)
