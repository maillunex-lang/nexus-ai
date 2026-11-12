"""Read bounded Godot workspace validation reports from a read-only mount."""
import json
import re
from pathlib import Path
from .mcp_principal import require_owner

ROOT=Path("/godot-workspaces")
JOB=re.compile(r"godot-[a-f0-9]{32}\Z")

def report(job_id:str)->dict:
    require_owner()
    if not isinstance(job_id,str) or not JOB.fullmatch(job_id):
        return {"error":"invalid_job_id"}
    folder=ROOT/job_id
    file=folder/"nexus_godot_report.json"
    if folder.is_symlink() or file.is_symlink() or not file.is_file() or file.stat().st_size>20_000:
        return {"error":"report_unavailable"}
    try:
        result=json.loads(file.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,ValueError):
        return {"error":"report_unreadable"}
    if result.get("job_id")!=job_id:
        return {"error":"report_mismatch"}
    return {"job_id":job_id,"passed":result.get("passed"),
            "godot_exit_code":result.get("godot_exit_code"),
            "timed_out":result.get("timed_out"),
            "source_files":result.get("source_files"),
            "patch_applied_to_copy":result.get("patch_applied_to_copy"),
            "original_modified":False,
            "godot_output":str(result.get("godot_output",""))[-6000:],
            "read_only":True}
