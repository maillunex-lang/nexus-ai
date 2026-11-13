"""Single-shot isolated Godot queue worker. Invoke with systemd timer, never as API.

Requires exclusive flock held by caller. No arbitrary paths or shell commands
are accepted from queue messages.
"""
import json
import os
import sys
import traceback
from pathlib import Path
from godot_agent_workspace import run
from godot_android_build import build as build_android
from godot_onboarding_worker import main as process_onboarding

BASE=Path("/opt/nexus-ai/godot-queue")
WORKSPACES=Path("/opt/nexus-ai/godot-workspaces")
PROJECTS={"basheco":Path("/opt/basheco/client"),
          "watermmo":Path("/opt/watermmo"),
          "agroempire":Path("/opt/fermabash/project")}
MAX_JOB=150000
MAX_BATCH=3

def process(file):
    job=file.stem
    if not job.startswith("godot-") or len(job)!=38 or any(c not in "0123456789abcdef" for c in job[6:]):
        return
    if file.is_symlink() or file.stat().st_size>MAX_JOB:
        return
    running=BASE/"running"/file.name
    os.rename(file,running)
    data={}
    try:
        data=json.loads(running.read_text(encoding="utf-8"))
        if data.get("job_id")!=job or data.get("project_id") not in PROJECTS:
            raise ValueError("invalid_job_or_project")
        if not isinstance(data.get("requested_by"),str) or len(data["requested_by"])>128:
            raise ValueError("invalid_requester")
        if set(data)=={"job_id","project_id","patches","requested_by"}:
            # Director change set: SHA-pinned modify/create/delete operations on one isolated copy.
            patch=data["patches"]
            if not isinstance(patch,list) or not patch:
                raise ValueError("invalid_job_shape")
        elif set(data)=={"job_id","project_id","path","expected_sha256","content","requested_by"}:
            patch={"path":data["path"],"expected_sha256":data["expected_sha256"],"content":data["content"]}
        else:
            raise ValueError("invalid_job_shape")
        report=run(PROJECTS[data["project_id"]],WORKSPACES,patch,timeout=120)
        result={"passed":report["passed"],"workspace_job_id":report["job_id"],
                "godot_exit_code":report["godot_exit_code"],
                "timed_out":report["timed_out"],"original_modified":False,
                "patched_files":report.get("patched_files"),
                "godot_script_errors":report.get("godot_script_errors"),
                "godot_output":report["godot_output"][-6000:]}
        state="completed" if report["passed"] else "failed"
    except Exception as exc:
        state="failed"
        result={"passed":False,"error":type(exc).__name__+":"+str(exc)[:240],
                "original_modified":False}
    output={"job_id":job,"requested_by":data.get("requested_by"),
            "result":result}
    destination=BASE/state/(job+".json")
    with destination.open("x",encoding="utf-8") as handle:
        json.dump(output,handle,ensure_ascii=False)
    running.unlink()

def process_build(file):
    job=file.stem
    if not job.startswith("godot-") or len(job)!=38 or any(c not in "0123456789abcdef" for c in job[6:]):
        return
    if file.is_symlink() or file.stat().st_size>MAX_JOB:
        return
    running=BASE/"build_running"/file.name
    os.rename(file,running)
    data={}
    try:
        data=json.loads(running.read_text(encoding="utf-8"))
        if data.get("kind")=="auto_android_debug_build":
            if set(data)!={"job_id","kind","project_id","requested_by"} or data.get("job_id")!=job:
                raise ValueError("invalid_auto_build_request")
            if data.get("project_id") not in PROJECTS:
                raise ValueError("project_not_allowlisted")
            if not isinstance(data.get("requested_by"),str) or not 1<=len(data["requested_by"])<=128:
                raise ValueError("invalid_requester")
            validation=run(PROJECTS[data["project_id"]],WORKSPACES,None,timeout=120)
            if not validation.get("passed"):
                raise ValueError("godot_validation_failed:"+str(validation.get("godot_output",""))[-200:])
            report=build_android(validation["job_id"])
            result={k:report.get(k) for k in ("passed","exit_code","timed_out","bytes","sha256","original_modified","published")}
            result["workspace_job_id"]=validation["job_id"]
            result["validation_passed"]=True
            result["project_id"]=data["project_id"]
            result["log"]=report.get("log","")[-3000:]
            state="build_completed" if report["passed"] else "build_failed"
        else:
            if set(data)!={"job_id","kind","validation_job_id","workspace_job_id","requested_by"}:
                raise ValueError("invalid_job_shape")
            if data["job_id"]!=job or data["kind"]!="android_debug_build":
                raise ValueError("invalid_job")
            validation_id=data["validation_job_id"]
            workspace_id=data["workspace_job_id"]
            if not isinstance(validation_id,str) or not validation_id.startswith("godot-") or len(validation_id)!=38:
                raise ValueError("invalid_validation_id")
            completed=BASE/"completed"/(validation_id+".json")
            if completed.is_symlink() or not completed.is_file():
                raise ValueError("validation_unavailable")
            validated=json.loads(completed.read_text(encoding="utf-8"))
            if validated.get("requested_by")!=data["requested_by"] or not validated.get("result",{}).get("passed"):
                raise ValueError("validation_owner_mismatch")
            if validated["result"].get("workspace_job_id")!=workspace_id:
                raise ValueError("workspace_mismatch")
            report=build_android(workspace_id)
            result={k:report.get(k) for k in ("passed","exit_code","timed_out","bytes","sha256","original_modified","published")}
            result["workspace_job_id"]=workspace_id
            result["log"]=report.get("log","")[-3000:]
            state="build_completed" if report["passed"] else "build_failed"
    except Exception as exc:
        state="build_failed"
        result={"passed":False,"error":type(exc).__name__+":"+str(exc)[:240],"published":False}
    destination=BASE/state/(job+".json")
    with destination.open("x",encoding="utf-8") as handle:
        json.dump({"job_id":job,"requested_by":data.get("requested_by"),"result":result},handle,ensure_ascii=False)
    running.unlink()

def main():
    for name in ("pending","running","completed","failed","build_pending","build_running","build_completed","build_failed"):
        (BASE/name).mkdir(parents=True,exist_ok=True)
    WORKSPACES.mkdir(parents=True,exist_ok=True)
    count=0
    for file in sorted((BASE/"pending").glob("godot-*.json")):
        if count>=MAX_BATCH:
            break
        process(file)
        count+=1
    for file in sorted((BASE/"build_pending").glob("godot-*.json"))[:1]:
        process_build(file)
        count+=1
    from godot_performance_worker import process_pending
    process_pending(BASE, WORKSPACES, PROJECTS)
    process_onboarding()
    print("processed",count)

if __name__=="__main__":
    main()
