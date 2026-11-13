from contextlib import asynccontextmanager
from urllib.parse import parse_qs
from pydantic import ValidationError, BaseModel
from typing import Literal
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
import os
from fastapi import FastAPI, Request, Response, Depends
from .mcp_server import mcp
from .db import database_ok
from .security import MCPBearerGuard
from .identity import LoginRequest, ChangePasswordRequest, change_own_password, login, logout, current_user
from .permissions import require_role
from .mission import overview as mission_overview
from .mission_workflow import ProjectCreate,TaskCreate,TaskUpdate,create_project,list_projects,create_task,list_tasks,update_task,director_plan
from uuid import UUID
from .director_approvals import Review,propose,list_proposals,review_proposal
from .director_queue import enqueue,list_jobs,cancel
from .agents import list_agents
from .oauth_server import AuthorizeRequest, TokenRequest, RevokeRequest, authorize, exchange, consent_preview, revoke_client_tokens

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        # Off by default; enabled only by NEXUS_DIRECTOR_TICK_SECONDS.
        from .director_scheduler import start as start_director_schedule
        schedule = start_director_schedule()
        try:
            yield
        finally:
            if schedule:
                schedule.cancel()

app = FastAPI(title="NEXUS AI Foundation", version="0.1.4-dev", lifespan=lifespan)
app.add_middleware(MCPBearerGuard)

@app.middleware("http")
async def reject_cross_origin_auth_writes(request: Request, call_next):
    if (request.url.path.startswith("/api/auth/") or request.url.path.startswith("/api/mission/") or request.url.path.startswith("/api/meshy/") or request.url.path.startswith("/api/dashboard/builds/") or request.url.path.startswith("/api/director/") or request.url.path in ("/oauth/authorize", "/oauth/revoke")) and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # Browsers sending cross-site form requests must not mutate sessions.
        fetch_site = request.headers.get("sec-fetch-site", "")
        if fetch_site == "cross-site":
            return Response(status_code=403, content="Cross-site request rejected")
        origin = request.headers.get("origin")
        host = request.headers.get("host", "")
        if origin and origin not in ("http://" + host, "https://" + host):
            return Response(status_code=403, content="Origin rejected")
    return await call_next(request)

@app.get("/api/health")
def health():
    return {"service": "nexus-ai", "status": "ok"}

@app.get("/api/status")
def status():
    return {"service": "nexus-ai", "version": "0.1.6-dev", "database": "connected" if database_ok() else "unavailable", "mcp": "protected", "security": "oauth-pkce" if os.environ.get("NEXUS_OAUTH_ISSUER") else "internal-only"}

@app.post("/api/auth/login")
def auth_login(payload: LoginRequest, response: Response):
    return login(payload, response)

@app.get("/api/auth/me")
def auth_me(request: Request):
    return current_user(request)

@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    return logout(request, response)

@app.post("/api/auth/change-password")
def auth_change_password(payload: ChangePasswordRequest, request: Request, response: Response):
    return change_own_password(payload, request, response)

@app.get("/api/mission/projects")
def mission_projects(request: Request):
    return list_projects(request)

@app.post("/api/mission/projects", status_code=201)
def mission_project_create(payload: ProjectCreate, request: Request):
    return create_project(payload,request)

@app.get("/api/mission/projects/{project_id}/tasks")
def mission_project_tasks(project_id: UUID, request: Request):
    return list_tasks(project_id,request)

@app.post("/api/mission/tasks", status_code=201)
def mission_task_create(payload: TaskCreate, request: Request):
    return create_task(payload,request)

@app.patch("/api/mission/tasks/{task_id}")
def mission_task_update(task_id: UUID, payload: TaskUpdate, request: Request):
    return update_task(task_id,payload,request)

@app.get("/api/mission/tasks/{task_id}/director-plan")
def mission_task_director_plan(task_id: UUID, request: Request):
    return director_plan(task_id,request)

@app.post("/api/mission/tasks/{task_id}/proposals", status_code=201)
def director_proposal_create(task_id: UUID, request: Request):
    return propose(task_id,request)

@app.get("/api/mission/projects/{project_id}/proposals")
def director_proposal_list(project_id: UUID, request: Request):
    return list_proposals(project_id,request)

@app.post("/api/mission/proposals/{proposal_id}/review")
def director_proposal_review(proposal_id: UUID, payload: Review, request: Request):
    return review_proposal(proposal_id,payload,request)

@app.post("/api/mission/proposals/{proposal_id}/enqueue", status_code=202)
def director_job_enqueue(proposal_id: UUID, request: Request):
    return enqueue(proposal_id,request)

@app.get("/api/mission/projects/{project_id}/jobs")
def director_jobs_list(project_id: UUID, request: Request):
    return list_jobs(project_id,request)

@app.post("/api/mission/jobs/{job_id}/cancel")
def director_job_cancel(job_id: UUID, request: Request):
    return cancel(job_id,request)

@app.get("/api/agents")
def agents_catalog(request: Request):
    return list_agents(request)

@app.get("/api/mission/overview")
def mission_control(request: Request):
    return mission_overview(request)

@app.get("/api/operator/overview")
def operator_overview(user: dict = Depends(require_role("owner", "operator", "viewer"))):
    return {"username": user["username"], "roles": user["roles"], "projects": "not-yet-enabled", "execution_enabled": False}

from .meshy_approvals import MeshyRequest, MeshyReview, create as create_meshy_request, review as review_meshy_request, list_requests as list_meshy_requests

@app.post("/api/meshy/requests", status_code=201)
def meshy_request_create(payload: MeshyRequest, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return create_meshy_request(payload,request)

@app.post("/api/meshy/requests/{request_id}/review")
def meshy_request_review(request_id: UUID, payload: MeshyReview, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return review_meshy_request(request_id,payload,request)

@app.get("/api/meshy/requests")
def meshy_requests(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return list_meshy_requests(request)

from .meshy_dispatch import dispatch as dispatch_meshy_preview, inspect as inspect_meshy_dispatch

@app.post("/api/meshy/requests/{request_id}/dispatch")
def meshy_dispatch_preview(request_id: UUID, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return dispatch_meshy_preview(request_id,request)

@app.get("/api/meshy/requests/{request_id}/status")
def meshy_dispatch_status(request_id: UUID, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return inspect_meshy_dispatch(request_id,request)

from .meshy_assets import glb_link as meshy_glb_link

@app.get("/api/meshy/requests/{request_id}/glb")
def meshy_request_glb(request_id: UUID, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return meshy_glb_link(request_id,request)

from .meshy_refine import RefineCreate, RefineReview, create as create_refine, review as review_refine, inspect as inspect_refine

@app.post("/api/meshy/refine", status_code=201)
def meshy_refine_create(payload: RefineCreate, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return create_refine(payload,request)

@app.post("/api/meshy/refine/{request_id}/review")
def meshy_refine_review(request_id: UUID, payload: RefineReview, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return review_refine(request_id,payload,request)

@app.get("/api/meshy/refine/{request_id}")
def meshy_refine_status(request_id: UUID, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return inspect_refine(request_id,request)

@app.get("/api/meshy/balance")
def meshy_owner_balance(response: Response, user: dict = Depends(require_role("owner"))):
    """Owner-only Meshy API balance. Never exposed via generic MCP read scope."""
    from .meshy_reader import balance
    response.headers["Cache-Control"] = "no-store"
    return balance()


@app.get("/api/meshy/tasks")
def meshy_owner_tasks(response: Response, user: dict = Depends(require_role("owner"))):
    """Owner-only sanitized task summaries; no model URLs or prompts."""
    from .meshy_reader import text_tasks
    response.headers["Cache-Control"] = "no-store"
    return text_tasks()


@app.get("/api/admin/overview")
def admin_overview(user: dict = Depends(require_role("owner"))):
    return {"username": user["username"], "management_enabled": False}

@app.get("/oauth/consent")
def oauth_consent(client_id: str, redirect_uri: str, request: Request, scope: str = "mcp:read"):
    return consent_preview(client_id, redirect_uri, request, scope)

@app.post("/oauth/revoke")
def oauth_revoke(payload: RevokeRequest, request: Request):
    return revoke_client_tokens(payload, request)

@app.get("/oauth/authorize")
def oauth_authorize_browser(request: Request):
    # The browser opens a same-origin SPA consent screen; no approval on GET.
    from urllib.parse import urlencode
    return RedirectResponse("/nexusai/?" + urlencode([("oauth", "1"), *request.query_params.multi_items()]), status_code=303)

@app.post("/oauth/authorize")
def oauth_authorize(payload: AuthorizeRequest, request: Request):
    return authorize(payload, request)

@app.post("/oauth/token")
async def oauth_token(request: Request):
    """OAuth RFC 6749 token endpoint: application/x-www-form-urlencoded only."""
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Expected form-encoded token request")
    raw = await request.body()
    if len(raw) > 8192:
        raise HTTPException(413, "Token request too large")
    try:
        data = parse_qs(raw.decode("utf-8"), keep_blank_values=True, strict_parsing=True)
        if any(len(values) != 1 for values in data.values()):
            raise ValueError("Duplicate parameter")
        payload = TokenRequest.model_validate({key: values[0] for key, values in data.items()})
    except (UnicodeDecodeError, ValueError, ValidationError):
        raise HTTPException(400, "Invalid token request")
    result = exchange(payload)
    return Response(content=__import__("json").dumps(result), media_type="application/json", headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


def configured_issuer() -> str:
    issuer = os.environ.get("NEXUS_OAUTH_ISSUER", "").rstrip("/")
    if not issuer.startswith("https://") or "?" in issuer or "#" in issuer:
        raise HTTPException(404, "OAuth discovery not configured")
    return issuer


@app.get("/.well-known/oauth-authorization-server")
def oauth_metadata():
    issuer = configured_issuer()
    return {
        "issuer": issuer,
        "authorization_endpoint": issuer + "/oauth/authorize",
        "token_endpoint": issuer + "/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp:read", "mcp:write"],
    }


@app.get("/.well-known/oauth-protected-resource")
def oauth_resource_metadata():
    issuer = configured_issuer()
    return {"resource": issuer + "/mcp/", "authorization_servers": [issuer],
            "scopes_supported": ["mcp:read", "mcp:write"], "bearer_methods_supported": ["header"]}

app.mount("/mcp", mcp.streamable_http_app())

from .meshy_refine_dispatch import dispatch as dispatch_refine, inspect as inspect_refine_dispatch

@app.post("/api/meshy/refine/{request_id}/dispatch")
def meshy_refine_dispatch(request_id: UUID, request: Request, response: Response):
    response.headers["Cache-Control"]="no-store"
    return dispatch_refine(request_id,request)

@app.get("/api/meshy/refine/{request_id}/dispatch-status")
def meshy_refine_dispatch_status(request_id: UUID, request: Request, response: Response):
    response.headers["Cache-Control"]="no-store"
    return inspect_refine_dispatch(request_id,request)

from .godot_apk_delivery import download as download_godot_apk

@app.get("/api/godot/builds/{build_job_id}/apk")
def godot_apk_download(build_job_id: str, expires: int, sha256: str, signature: str):
    return download_godot_apk(build_job_id,expires,sha256,signature)

# Session-authenticated build management; does not grant MCP OAuth write scope.
from . import dashboard_builds as dashboard_build

@app.get("/api/dashboard/builds/projects")
def dashboard_build_projects(request: Request):
    return dashboard_build.projects(request)

@app.post("/api/dashboard/builds/projects/{project_id}")
def dashboard_build_start(project_id: str, request: Request):
    return dashboard_build.enqueue(request, project_id)

@app.get("/api/dashboard/builds/jobs/{job_id}")
def dashboard_build_status(job_id: str, request: Request):
    return dashboard_build.check(request, job_id)

@app.post("/api/dashboard/builds/jobs/{job_id}/download")
def dashboard_build_link(job_id: str, request: Request):
    return dashboard_build.link(request, job_id)

# Owner-reviewed MCP proposals; read OAuth tokens cannot execute these actions.
from . import director_requests as approval_requests

@app.get("/api/director/requests")
def director_request_list(request: Request):
    return approval_requests.list_pending(request)

@app.get("/api/director/requests/{request_id}")
def director_request_detail(request_id: str, request: Request):
    return approval_requests.get(request_id,request)

@app.post("/api/director/requests/{request_id}/download")
def director_request_download(request_id: str, request: Request):
    return approval_requests.download_link(request_id,request)

class DirectorApprovalDecision(BaseModel):
    decision: Literal["approved","denied"]

@app.post("/api/director/requests/{request_id}/review")
def director_request_review(request_id: str, payload: DirectorApprovalDecision, request: Request):
    return approval_requests.review(request_id,payload.decision,request)

# Owner-session Director console: pipelines, agents and the error journal.
from . import dashboard_director

class DirectorPipelineLaunch(BaseModel):
    pipeline: str
    project_id: str
    changeset_id: str = ""
    task_id: str = ""

class DirectorChangeValidation(BaseModel):
    project_id: str
    enabled: bool

@app.get("/api/director/settings")
def director_settings_read(request: Request):
    return dashboard_director.settings(request)

@app.post("/api/director/settings/change-validation")
def director_settings_change_validation(payload: DirectorChangeValidation, request: Request):
    return dashboard_director.set_change_validation(request, payload.project_id, payload.enabled)

@app.get("/api/director/agents")
def director_agents(request: Request):
    return dashboard_director.agents(request)

@app.get("/api/director/catalog")
def director_catalog(request: Request):
    return dashboard_director.catalog(request)

@app.get("/api/director/errors")
def director_errors_list(request: Request, limit: int = 20, project_id: str = ""):
    return dashboard_director.errors(request, limit, project_id)

@app.get("/api/director/pipelines")
def director_pipeline_list(request: Request, state: str = "", task_id: str = ""):
    return dashboard_director.pipelines(request, state, task_id)

@app.post("/api/director/pipelines", status_code=202)
def director_pipeline_launch(payload: DirectorPipelineLaunch, request: Request):
    return dashboard_director.launch(request, payload.pipeline, payload.project_id, payload.changeset_id, payload.task_id)

@app.get("/api/director/pipelines/{pipeline_id}")
def director_pipeline_detail(pipeline_id: str, request: Request):
    return dashboard_director.detail(request, pipeline_id)

@app.get("/api/director/pipelines/{pipeline_id}/journal")
def director_pipeline_journal(pipeline_id: str, request: Request):
    return dashboard_director.journal(request, pipeline_id)

@app.post("/api/director/pipelines/{pipeline_id}/cancel")
def director_pipeline_cancel(pipeline_id: str, request: Request):
    return dashboard_director.cancel(request, pipeline_id)

@app.post("/api/director/pipelines/{pipeline_id}/retry")
def director_pipeline_retry(pipeline_id: str, request: Request):
    return dashboard_director.retry(request, pipeline_id)
