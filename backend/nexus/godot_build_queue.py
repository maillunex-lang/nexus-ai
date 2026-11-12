"""Owner-authorized Android debug build requests for validated Godot jobs."""
import json
import os
import uuid
from pathlib import Path
from .godot_job_queue import QUEUE,JOBS,status as validation_status
from .mcp_principal import require_owner,require_owner_write

def submit(validation_job_id:str)->dict:
    principal=require_owner_write()
    validation=validation_status(validation_job_id)
    if validation.get("state")!="completed" or not validation.get("result",{}).get("passed"):
        return {"error":"validated_owned_job_required"}
    workspace_id=validation["result"].get("workspace_job_id")
    if not isinstance(workspace_id,str) or not JOBS.fullmatch(workspace_id):
        return {"error":"invalid_workspace"}
    # Reuse only this owner's successful queue result, never arbitrary workspace IDs.
    job_id="godot-"+uuid.uuid4().hex
    request={"job_id":job_id,"kind":"android_debug_build",
             "validation_job_id":validation_job_id,
             "workspace_job_id":workspace_id,
             "requested_by":str(principal["user_id"])}
    folder=QUEUE/"build_pending"
    folder.mkdir(parents=True,exist_ok=True)
    fd=os.open(str(folder/(job_id+".json")),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as handle:
        json.dump(request,handle)
    return {"job_id":job_id,"state":"queued","kind":"android_debug_build",
            "published":False,"original_modified":False}

def status(job_id:str)->dict:
    principal=require_owner()
    if not isinstance(job_id,str) or not JOBS.fullmatch(job_id):
        return {"error":"invalid_job_id"}
    for state in ("build_completed","build_failed","build_running","build_pending"):
        file=QUEUE/state/(job_id+".json")
        if file.is_symlink() or not file.is_file() or file.stat().st_size>20000:
            continue
        try:
            payload=json.loads(file.read_text(encoding="utf-8"))
        except (ValueError,OSError):
            return {"error":"invalid_result"}
        if payload.get("requested_by")!=str(principal["user_id"]):
            return {"error":"not_found"}
        result={"job_id":job_id,"state":state.removeprefix("build_")}
        if state in ("build_completed","build_failed"):
            result["result"]=payload.get("result",{})
        return result
    return {"error":"not_found"}
