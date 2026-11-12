"""AI-free multi-workflow director with owner-scoped durable JSONL journal.

The underlying Godot worker performs the actual transitions for build jobs.
This module observes those transitions and reports deterministic error policy.
"""
import json
import os
import re
import uuid
from datetime import datetime,timezone
from pathlib import Path
from .godot_job_queue import QUEUE
from .godot_projects import PROJECTS,inspect_project
from .godot_one_command import start as build_start
from .godot_build_queue import status as build_status
from .godot_project_onboarding import request as register_start,status as register_status
from .mcp_principal import require_owner,require_owner_write

BASE=QUEUE/"director"
JOB=re.compile(r"director-[0-9a-f]{32}\Z")
WORKFLOWS={
 "inspect_project":["inventory","static_analysis","report"],
 "validate_and_build_android":["isolated_copy","godot_validation","android_debug_export","checksum"],
 "register_github":["validate_source","clone_snapshot","inspect","register"],
 "register_lunex":["validate_source","copy_snapshot","inspect","register"],
 "create_godot_project":["validate_title","create_template","register"],
}
ERROR_POLICY={
 "invalid_request":"reject_without_retry",
 "project_not_build_enabled":"reject_without_retry",
 "source_unavailable":"stop_and_report",
 "godot_validation_failed":"stop_and_report",
 "build_failed":"stop_and_report",
 "worker_timeout":"stop_and_report",
 "default":"stop_and_report",
}
MAX_LOG=100
def _stamp():
 return datetime.now(timezone.utc).isoformat()
def _write(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"w",encoding="utf-8") as f:json.dump(data,f,ensure_ascii=False)
def _read(job_id,user):
 if not isinstance(job_id,str) or not JOB.fullmatch(job_id):return None
 path=BASE/(job_id+".json")
 if path.is_symlink() or not path.is_file() or path.stat().st_size>12000:return None
 try:data=json.loads(path.read_text())
 except (OSError,ValueError):return None
 if data.get("owner")!=str(user["user_id"]):return None
 return data
def _append(job_id,event):
 folder=BASE/"events"
 folder.mkdir(parents=True,exist_ok=True)
 path=folder/(job_id+".jsonl")
 if path.is_symlink():raise ValueError("invalid_journal")
 fd=os.open(str(path),os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"a",encoding="utf-8") as f:f.write(json.dumps({"time":_stamp(),**event},ensure_ascii=False)+"\n")

def launch(workflow:str,project_id:str,source:str="")->dict:
 user=require_owner_write()
 if workflow not in WORKFLOWS:return {"error":"unsupported_workflow","supported":sorted(WORKFLOWS)}
 if not isinstance(project_id,str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,39}",project_id):
  return {"error":"invalid_project_id"}
 if workflow in ("inspect_project","validate_and_build_android") and source:
  return {"error":"unexpected_source"}
 if workflow=="inspect_project":
  try:report=inspect_project(project_id)
  except (ValueError,OSError):return {"error":"project_unavailable"}
  underlying=None
 elif workflow=="validate_and_build_android":
  result=build_start(project_id)
  if result.get("error"):return result
  underlying=result["job_id"]
 elif workflow in ("register_github","register_lunex","create_godot_project"):
  if not isinstance(source,str) or not source:return {"error":"source_required"}
  kind={"register_github":"github","register_lunex":"lunex","create_godot_project":"template"}[workflow]
  result=register_start(project_id,kind,source)
  if result.get("error"):return result
  underlying=result["job_id"]
 job_id="director-"+uuid.uuid4().hex
 record={"job_id":job_id,"owner":str(user["user_id"]),"workflow":workflow,
         "project_id":project_id,"underlying":underlying,"created_at":_stamp(),
         "state":"completed" if workflow=="inspect_project" else "queued",
         "steps":WORKFLOWS[workflow]}
 _write(BASE/(job_id+".json"),record)
 _append(job_id,{"event":"created","state":record["state"],"workflow":workflow})
 if workflow=="inspect_project":
  _append(job_id,{"event":"completed","step":"report","files":report.get("file_count")})
 return {"director_job_id":job_id,"state":record["state"],"workflow":workflow,
         "steps":record["steps"],"published":False,"source_modified":False}

def _evaluate(record):
 workflow=record["workflow"]
 if workflow=="inspect_project":
  return {"state":"completed","step":"report","passed":True}
 if workflow=="validate_and_build_android":
  status=build_status(record["underlying"])
 else:
  status=register_status(record["underlying"])
 state=status.get("state")
 if status.get("error"):return {"state":"failed","error":"underlying_job_unavailable","policy":"stop_and_report"}
 if state in ("queued","pending"):return {"state":"queued","step":record["steps"][0]}
 if state=="running":return {"state":"running","step":record["steps"][1]}
 if state=="completed":
  result=status.get("result",{})
  passed=bool(result.get("passed")) if workflow=="validate_and_build_android" else bool(result.get("registered"))
  if passed:
   response={"state":"completed","step":record["steps"][-1],"passed":True}
   if workflow=="validate_and_build_android":
    response.update({"bytes":result.get("bytes"),"sha256":result.get("sha256"),
                     "next_tool":"nexus_godot_apk_download_link","build_job_id":record["underlying"]})
   return response
  state="failed"
 if state=="failed":
  error=str((status.get("result") or {}).get("error") or "build_failed")[:200]
  key=next((k for k in ERROR_POLICY if k!="default" and k in error),"default")
  return {"state":"failed","step":"stopped","passed":False,"error":error,
          "policy":ERROR_POLICY[key],"auto_retry":False}
 return {"state":"queued","step":record["steps"][0]}

def inspect(job_id:str)->dict:
 user=require_owner()
 record=_read(job_id,user)
 if record is None:return {"error":"not_found"}
 result=_evaluate(record)
 return {"director_job_id":job_id,"workflow":record["workflow"],
         "project_id":record["project_id"],**result,
         "published":False,"source_modified":False}

def journal(job_id:str)->dict:
 user=require_owner()
 record=_read(job_id,user)
 if record is None:return {"error":"not_found"}
 path=BASE/"events"/(job_id+".jsonl")
 if path.is_symlink():return {"error":"invalid_journal"}
 try:events=[json.loads(line) for line in path.read_text().splitlines()[-MAX_LOG:]]
 except (OSError,ValueError):events=[]
 return {"director_job_id":job_id,"events":events,"current":inspect(job_id)}

def workflows()->dict:
 require_owner()
 return {"mode":"rules_only","external_ai_api":False,"workflows":WORKFLOWS,
         "error_policy":ERROR_POLICY,"automatic_transitions":True,
         "automatic_code_fix":False,"automatic_publish":False}
