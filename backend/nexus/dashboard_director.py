"""Owner browser-session access to the Director console; separate from MCP OAuth grants.

Reads use a read-scoped principal. Launch, cancel and retry are explicit owner
actions in an authenticated same-origin session, so they run with write scope.
"""
from fastapi import HTTPException, Request
from . import director_errors, director_pipelines
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


def pipelines(request: Request, state: str) -> dict:
    return _call(request, "mcp:read", director_pipelines.list_pipelines, state)


def detail(request: Request, pipeline_id: str) -> dict:
    return _call(request, "mcp:read", director_pipelines.status, pipeline_id)


def journal(request: Request, pipeline_id: str) -> dict:
    return _call(request, "mcp:read", director_pipelines.journal, pipeline_id)


def launch(request: Request, pipeline: str, project_id: str, changeset_id: str) -> dict:
    return _call(request, "mcp:write", director_pipelines.launch, pipeline, project_id, changeset_id)


def cancel(request: Request, pipeline_id: str) -> dict:
    return _call(request, "mcp:write", director_pipelines.cancel, pipeline_id)


def retry(request: Request, pipeline_id: str) -> dict:
    return _call(request, "mcp:write", director_pipelines.retry, pipeline_id)
