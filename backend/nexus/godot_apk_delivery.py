"""Short-lived owner-issued APK download links, bound to an immutable build result.

The link is a 5-minute bearer capability. It never includes server paths, user
identity or credentials. Do not log or publish the link.
"""
import hashlib
import hmac
import os
import re
import time
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse
from .godot_build_queue import status
from .godot_job_queue import QUEUE,JOBS
from .mcp_principal import require_owner

WORKSPACES=Path("/godot-workspaces")
TTL=300
SHA=re.compile(r"[0-9a-f]{64}\Z")
MAX_APK=250*1024*1024

def _key():
    secret=os.environ.get("NEXUS_MCP_INTERNAL_TOKEN","")
    if len(secret)<32:
        raise RuntimeError("download_signing_key_unavailable")
    return hashlib.sha256(b"nexus-apk-download-v1\x00"+secret.encode()).digest()

def _signature(job_id,expiry,digest):
    message=f"{job_id}:{expiry}:{digest}".encode("ascii")
    return hmac.new(_key(),message,hashlib.sha256).hexdigest()

def issue(build_job_id:str)->dict:
    require_owner()
    build=status(build_job_id)
    if build.get("state")!="completed" or not build.get("result",{}).get("passed"):
        return {"error":"completed_owned_build_required"}
    result=build["result"]
    workspace=result.get("workspace_job_id")
    digest=result.get("sha256")
    if not isinstance(workspace,str) or not JOBS.fullmatch(workspace) or not isinstance(digest,str) or not SHA.fullmatch(digest):
        return {"error":"invalid_build_result"}
    expiry=int(time.time())+TTL
    signature=_signature(build_job_id,expiry,digest)
    path=f"/nexusai/api/godot/builds/{build_job_id}/apk?expires={expiry}&sha256={digest}&signature={signature}"
    return {"download_url":path,"expires_at_unix":expiry,"ttl_seconds":TTL,
            "sha256":digest,"bytes":result.get("bytes"),"published":False,
            "note":"Private bearer link; expires in five minutes. Do not share."}

def download(build_job_id:str,expires:int,sha256:str,signature:str):
    if not JOBS.fullmatch(build_job_id) or not SHA.fullmatch(sha256) or not SHA.fullmatch(signature):
        raise HTTPException(404,"Not found")
    now=int(time.time())
    if expires<now or expires>now+TTL:
        raise HTTPException(403,"Download link expired")
    if not hmac.compare_digest(_signature(build_job_id,expires,sha256),signature):
        raise HTTPException(403,"Invalid download signature")
    result_file=QUEUE/"build_completed"/(build_job_id+".json")
    if result_file.is_symlink() or not result_file.is_file() or result_file.stat().st_size>20000:
        raise HTTPException(404,"Build not found")
    import json
    try:
        payload=json.loads(result_file.read_text(encoding="utf-8"))
    except (OSError,ValueError):
        raise HTTPException(404,"Build not found")
    if payload.get("job_id")!=build_job_id or not payload.get("requested_by"):
        raise HTTPException(404,"Build not found")
    result=payload.get("result",{})
    workspace_id=result.get("workspace_job_id")
    if not result.get("passed") or result.get("sha256")!=sha256 or not isinstance(workspace_id,str) or not JOBS.fullmatch(workspace_id):
        raise HTTPException(404,"Artifact not found")
    folder=WORKSPACES/workspace_id
    apk=folder/"nexus-build"/"android-debug.apk"
    if folder.is_symlink() or apk.parent.is_symlink() or apk.is_symlink() or not apk.is_file():
        raise HTTPException(404,"Artifact not found")
    if not 0<apk.stat().st_size<=MAX_APK or apk.stat().st_size!=result.get("bytes"):
        raise HTTPException(409,"Artifact size mismatch")
    with apk.open("rb") as handle:
        digest=hashlib.file_digest(handle,"sha256").hexdigest()
    if not hmac.compare_digest(digest,sha256):
        raise HTTPException(409,"Artifact checksum mismatch")
    return FileResponse(apk,media_type="application/vnd.android.package-archive",
        filename="BASHECO-debug-"+build_job_id[6:14]+".apk",
        headers={"Cache-Control":"private, no-store, max-age=0",
                 "X-Content-Type-Options":"nosniff",
                 "Referrer-Policy":"no-referrer",
                 "Content-Security-Policy":"default-src 'none'"})
