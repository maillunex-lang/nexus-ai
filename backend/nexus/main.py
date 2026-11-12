from contextlib import asynccontextmanager
from urllib.parse import parse_qs
from pydantic import ValidationError
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
        yield

app = FastAPI(title="NEXUS AI Foundation", version="0.1.4-dev", lifespan=lifespan)
app.add_middleware(MCPBearerGuard)

@app.middleware("http")
async def reject_cross_origin_auth_writes(request: Request, call_next):
    if (request.url.path.startswith("/api/auth/") or request.url.path.startswith("/api/mission/") or request.url.path in ("/oauth/authorize", "/oauth/revoke")) and request.method in ("POST", "PUT", "PATCH", "DELETE"):
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

@app.get("/api/meshy/balance")
def meshy_owner_balance(user: dict = Depends(require_role("owner"))):
    """Owner-only Meshy API balance. Never exposed via generic MCP read scope."""
    from .meshy_reader import balance
    return balance()


@app.get("/api/meshy/tasks")
def meshy_owner_tasks(user: dict = Depends(require_role("owner"))):
    """Owner-only sanitized task summaries; no model URLs or prompts."""
    from .meshy_reader import text_tasks
    return text_tasks()


@app.get("/api/admin/overview")
def admin_overview(user: dict = Depends(require_role("owner"))):
    return {"username": user["username"], "management_enabled": False}

@app.get("/oauth/consent")
def oauth_consent(client_id: str, redirect_uri: str, request: Request):
    return consent_preview(client_id, redirect_uri, request)

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
        "scopes_supported": ["mcp:read"],
    }


@app.get("/.well-known/oauth-protected-resource")
def oauth_resource_metadata():
    issuer = configured_issuer()
    return {"resource": issuer + "/mcp/", "authorization_servers": [issuer],
            "scopes_supported": ["mcp:read"], "bearer_methods_supported": ["header"]}

app.mount("/mcp", mcp.streamable_http_app())
