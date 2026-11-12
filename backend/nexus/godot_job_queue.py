"""MCP-to-host Godot execution handoff via a bounded file queue.

The API can write ONLY queue requests, not execute host commands. The separate
host worker validates project identifiers and writes result files.
"""
import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from .mcp_principal import require_owner,require_owner_write
from .godot_projects import _root,_read
from .godot_change_preview import EDITABLE,preview

QUEUE=Path("/godot-queue")
JOBS=re.compile(r"godot-[a-f0-9]{32}\Z")
MAX_CONTENT=100_000

def submit(project_id:str,relative_path:str,expected_sha256:str,proposed_content:str)->dict:
    principal=require_owner_write()
    if project_id!="basheco":
        return {"error":"unknown_project"}
    if not isinstance(proposed_content,str) or len(proposed_content.encode("utf-8"))>MAX_CONTENT:
        return {"error":"content_too_large"}
    proposed=preview(project_id,relative_path,expected_sha256,proposed_content)
    if proposed.get("error"):
        return proposed
    if not proposed["changed"]:
        return {"error":"no_changes"}
    # The API only deposits a file. The host worker rechecks all source hashes.
    job="godot-"+uuid.uuid4().hex
    payload={"job_id":job,"project_id":project_id,"path":relative_path,
             "expected_sha256":expected_sha256,"content":proposed_content,
             "requested_by":str(principal["user_id"])}
    directory=QUEUE/"pending"
    directory.mkdir(parents=True,exist_ok=True)
    final=directory/(job+".json")
    fd=os.open(str(final),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as file:
            json.dump(payload,file,ensure_ascii=False)
    except BaseException:
        final.unlink(missing_ok=True)
        raise
    return {"job_id":job,"state":"queued","source_project_modified":False,
            "diff":proposed["diff"],"proposed_sha256":proposed["proposed_sha256"]}

def status(job_id:str)->dict:
    principal=require_owner()
    if not isinstance(job_id,str) or not JOBS.fullmatch(job_id):
        return {"error":"invalid_job_id"}
    for state in ("completed","failed"):
        file=QUEUE/state/(job_id+".json")
        if file.is_symlink() or not file.is_file() or file.stat().st_size>20000:
            continue
        try:
            data=json.loads(file.read_text())
        except (OSError,ValueError):
            return {"error":"invalid_result"}
        if data.get("requested_by")!=str(principal["user_id"]):
            return {"error":"not_found"}
        return {"job_id":job_id,"state":state,"result":data.get("result",{})}
    # Pending jobs must also be scoped to the requesting owner.
    for state in ("pending","running"):
        file=QUEUE/state/(job_id+".json")
        if file.is_symlink() or not file.is_file() or file.stat().st_size>150000:
            continue
        try:
            data=json.loads(file.read_text())
        except (OSError,ValueError):
            return {"error":"invalid_job"}
        if data.get("requested_by")!=str(principal["user_id"]):
            return {"error":"not_found"}
        return {"job_id":job_id,"state":state}
    return {"error":"not_found"}
