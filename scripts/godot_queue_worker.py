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

BASE=Path("/opt/nexus-ai/godot-queue")
WORKSPACES=Path("/opt/nexus-ai/godot-workspaces")
PROJECTS={"basheco":Path("/opt/basheco/client")}
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
        if set(data)!={"job_id","project_id","path","expected_sha256","content","requested_by"}:
            raise ValueError("invalid_job_shape")
        patch={"path":data["path"],"expected_sha256":data["expected_sha256"],"content":data["content"]}
        report=run(PROJECTS[data["project_id"]],WORKSPACES,patch,timeout=120)
        result={"passed":report["passed"],"workspace_job_id":report["job_id"],
                "godot_exit_code":report["godot_exit_code"],
                "timed_out":report["timed_out"],"original_modified":False,
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

def main():
    for name in ("pending","running","completed","failed"):
        (BASE/name).mkdir(parents=True,exist_ok=True)
    WORKSPACES.mkdir(parents=True,exist_ok=True)
    count=0
    for file in sorted((BASE/"pending").glob("godot-*.json")):
        if count>=MAX_BATCH:
            break
        process(file)
        count+=1
    print("processed",count)

if __name__=="__main__":
    main()
