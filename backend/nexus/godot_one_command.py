"""One-command owner-authorized validation and Android debug APK build.

Only explicitly allowlisted projects. No source edits, release signing or
publishing. The caller polls nexus_godot_build_status and can then request a
five-minute link using nexus_godot_apk_download_link.
"""
import json
import os
import uuid
from .godot_build_queue import status
from .godot_job_queue import QUEUE
from .godot_projects import PROJECTS,_root
from .mcp_principal import require_owner_write

def start(project_id:str)->dict:
    owner=require_owner_write()
    if not isinstance(project_id,str) or project_id not in PROJECTS:
        return {"error":"unknown_or_unconfigured_project","available_projects":sorted(PROJECTS)}
    try:
        _root(project_id)
    except ValueError:
        return {"error":"project_unavailable"}
    job_id="godot-"+uuid.uuid4().hex
    request={"job_id":job_id,"kind":"auto_android_debug_build",
             "project_id":project_id,"requested_by":str(owner["user_id"])}
    folder=QUEUE/"build_pending"
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(job_id+".json")
    fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as file:
            json.dump(request,file)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {"job_id":job_id,"state":"queued","project_id":project_id,
            "steps":["isolated_copy","godot_validation","android_debug_export","checksum"],
            "source_modified":False,"published":False,
            "next_tool":"nexus_godot_build_status"}

def check(job_id:str)->dict:
    return status(job_id)
