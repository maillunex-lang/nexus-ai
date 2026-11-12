"""Rule-based AI-free director for safe, bounded Godot build workflows.

No LLM, API key, arbitrary shell, code edits, deployment or publication.
"""
import re
from .godot_projects import PROJECTS
from .godot_one_command import start as queue_build
from .godot_build_queue import status as build_status
from .mcp_principal import require_owner, require_owner_write

WORKFLOWS={
    "validate_and_build_android":{
        "description":"Изолированная копия -> Godot проверка -> Android debug APK -> SHA-256",
        "steps":["isolated_copy","godot_validation","android_debug_export","checksum"],
        "publishes":False,"modifies_original":False,
    }
}
JOB=re.compile(r"godot-[0-9a-f]{32}\Z")

def capabilities()->dict:
    require_owner()
    return {"mode":"deterministic_rules","local_llm":False,"external_ai_api":False,
            "workflows":WORKFLOWS,"build_enabled_projects":sorted(PROJECTS),
            "requires_owner_write":True,"source_modified":False,
            "auto_publish":False,"arbitrary_code_execution":False}

def run(project_id:str,workflow:str="validate_and_build_android")->dict:
    require_owner_write()
    if workflow not in WORKFLOWS:
        return {"error":"unsupported_workflow","supported_workflows":sorted(WORKFLOWS)}
    if not isinstance(project_id,str) or project_id not in PROJECTS:
        return {"error":"project_not_build_enabled","available_projects":sorted(PROJECTS)}
    result=queue_build(project_id)
    if result.get("state")!="queued":
        return result
    return {"director_job_id":result["job_id"],"project_id":project_id,
            "workflow":workflow,"state":"queued","steps":WORKFLOWS[workflow]["steps"],
            "source_modified":False,"published":False,
            "next_tool":"nexus_director_status"}

def check(job_id:str)->dict:
    require_owner()
    if not isinstance(job_id,str) or not JOB.fullmatch(job_id):
        return {"error":"invalid_job_id"}
    result=build_status(job_id)
    if result.get("error"):
        return result
    state=result["state"]
    report=result.get("result",{})
    response={"director_job_id":job_id,"state":state,
              "workflow":"validate_and_build_android",
              "passed":report.get("passed") if state in ("completed","failed") else None,
              "published":False,"source_modified":False}
    if state=="completed" and report.get("passed"):
        response.update({"bytes":report.get("bytes"),"sha256":report.get("sha256"),
                         "next_tool":"nexus_godot_apk_download_link"})
    elif state=="failed":
        response["error"]=report.get("error") or "validation_or_build_failed"
        response["next_action"]="inspect_error_and_request_explicit_fix"
    return response
