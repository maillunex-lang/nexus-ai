"""Owner browser-session access to the Director console; separate from MCP OAuth grants.

Reads use a read-scoped principal. Launch, cancel and retry are explicit owner
actions in an authenticated same-origin session, so they run with write scope.
"""
from fastapi import HTTPException, Request
from . import director_adoption, director_errors, director_pipelines, director_settings
from .identity import current_user
from .mcp_principal import principal_var


def _call(request: Request, scope: str, function, *args):
    user = current_user(request)
    if "owner" not in user["roles"]:
        raise HTTPException(403, "Owner role required")
    token = principal_var.set({"user_id": str(user["id"]), "roles": ["owner"], "scope": scope})
    try:
        return function(*args)
    finally:
        principal_var.reset(token)


def agents(request: Request) -> dict:
    return _call(request, "mcp:read", director_pipelines.agents)


def catalog(request: Request) -> dict:
    return _call(request, "mcp:read", director_pipelines.catalog)


def errors(request: Request, limit: int, project_id: str) -> dict:
    return _call(request, "mcp:read", director_errors.list_errors, limit, project_id)


def pipelines(request: Request, state: str, task_id: str = "") -> dict:
    return _call(request, "mcp:read", director_pipelines.list_pipelines, state, task_id)


def detail(request: Request, pipeline_id: str) -> dict:
    return _call(request, "mcp:read", director_pipelines.status, pipeline_id)


def journal(request: Request, pipeline_id: str) -> dict:
    return _call(request, "mcp:read", director_pipelines.journal, pipeline_id)


def launch(request: Request, pipeline: str, project_id: str, changeset_id: str, task_id: str = "") -> dict:
    return _call(request, "mcp:write", director_pipelines.launch, pipeline, project_id, changeset_id, "", task_id)


def settings(request: Request) -> dict:
    return _call(request, "mcp:read", director_settings.describe)


def set_change_validation(request: Request, project_id: str, enabled: bool) -> dict:
    return _call(request, "mcp:write", director_settings.set_change_enabled, project_id, enabled)


def cancel(request: Request, pipeline_id: str) -> dict:
    return _call(request, "mcp:write", director_pipelines.cancel, pipeline_id)


def retry(request: Request, pipeline_id: str) -> dict:
    return _call(request, "mcp:write", director_pipelines.retry, pipeline_id)


def adoption(request: Request) -> dict:
    return _call(request, "mcp:read", director_adoption.describe)


def changeset_patch(request: Request, changeset_id: str) -> dict:
    return _call(request, "mcp:read", director_adoption.patch, changeset_id)
