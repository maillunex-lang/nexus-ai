"""Owner-only project onboarding requests; host worker validates sources.

Registration does not automatically grant build permission.
"""
import json
import os
import re
import uuid
from pathlib import Path
from .godot_job_queue import QUEUE
from .mcp_principal import require_owner,require_owner_write

ID=re.compile(r"[a-z][a-z0-9-]{2,39}\Z")
GITHUB=re.compile(r"(?:https://github\.com/)?([A-Za-z0-9_.-]{1,39})/([A-Za-z0-9_.-]{1,100})(?:\.git)?\Z")
HOST_ROOTS=("/opt/","/home/gamedev/projects/")

def request(project_id:str,source_type:str,source:str)->dict:
    user=require_owner_write()
    if not isinstance(project_id,str) or not ID.fullmatch(project_id):
        return {"error":"invalid_project_id"}
    if source_type=="github":
        if not isinstance(source,str) or not GITHUB.fullmatch(source) or ".." in source:
            return {"error":"invalid_github_repository"}
        match=GITHUB.fullmatch(source)
        source=f"https://github.com/{match.group(1)}/{match.group(2).removesuffix('.git')}.git"
    elif source_type=="lunex":
        if not isinstance(source,str) or not source.startswith(HOST_ROOTS) or ".." in Path(source).parts or len(source)>240:
            return {"error":"invalid_lunex_path"}
        if source.startswith("/opt/nexus-ai/"):
            return {"error":"reserved_path"}
    else:
        return {"error":"unsupported_source_type"}
    job="onboard-"+uuid.uuid4().hex
    folder=QUEUE/"onboard_pending"
    folder.mkdir(parents=True,exist_ok=True)
    fd=os.open(str(folder/(job+".json")),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"w") as handle:
        json.dump({"job_id":job,"project_id":project_id,"source_type":source_type,
                   "source":source,"requested_by":str(user["user_id"])},handle)
    return {"job_id":job,"state":"queued","build_enabled":False,
            "note":"Public GitHub repositories only in this version. New projects are inspected but not automatically build-enabled."}

def status(job_id:str)->dict:
    user=require_owner()
    if not isinstance(job_id,str) or not re.fullmatch(r"onboard-[0-9a-f]{32}",job_id):
        return {"error":"invalid_job_id"}
    for state in ("onboard_completed","onboard_failed","onboard_running","onboard_pending"):
        path=QUEUE/state/(job_id+".json")
        if path.is_symlink() or not path.is_file() or path.stat().st_size>20000:
            continue
        try:
            data=json.loads(path.read_text())
        except (ValueError,OSError):
            return {"error":"invalid_job"}
        if data.get("requested_by")!=str(user["user_id"]):
            return {"error":"not_found"}
        return {"job_id":job_id,"state":state.removeprefix("onboard_"),
                "result":data.get("result")}
    return {"error":"not_found"}

def list_registered()->dict:
    """List completed inspection-only project registrations owned by caller."""
    owner=require_owner()
    directory=QUEUE/"onboard_completed"
    projects=[]
    if directory.is_dir():
        for path in sorted(directory.glob("onboard-*.json"))[:200]:
            if path.is_symlink() or path.stat().st_size>20000:
                continue
            try:
                item=json.loads(path.read_text())
            except (OSError,ValueError):
                continue
            if item.get("requested_by")!=str(owner["user_id"]):
                continue
            result=item.get("result") or {}
            if result.get("registered"):
                projects.append({"project_id":result.get("project_id"),
                                 "files":result.get("files"),
                                 "bytes":result.get("bytes"),
                                 "build_enabled":False,
                                 "inspection_only":True})
    return {"projects":projects}
