"""Owner session authorized build controls; separate from MCP OAuth grants."""
from fastapi import HTTPException, Request
from .identity import current_user
from .mcp_principal import principal_var
from .godot_projects import PROJECTS, _root
from .godot_one_command import start
from .godot_build_queue import status
from .godot_apk_delivery import issue

def _owner(request: Request):
    user=current_user(request)
    if "owner" not in user["roles"]:
        raise HTTPException(403,"Owner role required")
    return user

def projects(request:Request)->dict:
    _owner(request)
    return {"projects":[{"id":id,"name":entry["name"],"available":_available(id)}
                        for id,entry in PROJECTS.items()],"build_type":"android_debug",
            "originals_modified":False}

def _available(project_id):
    try:_root(project_id);return True
    except ValueError:return False

def _call(request,func,*args):
    user=_owner(request)
    token=principal_var.set({"user_id":user["id"],"roles":user["roles"],"scope":"mcp:write"})
    try:return func(*args)
    finally:principal_var.reset(token)

def enqueue(request:Request,project_id:str)->dict:
    if project_id not in PROJECTS:raise HTTPException(404,"Unknown build project")
    return _call(request,start,project_id)

def check(request:Request,job_id:str)->dict:
    return _call(request,status,job_id)

def link(request:Request,job_id:str)->dict:
    return _call(request,issue,job_id)
