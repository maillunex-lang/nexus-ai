from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, Depends
from .mcp_server import mcp
from .db import database_ok
from .security import MCPBearerGuard
from .identity import LoginRequest, login, logout, current_user
from .permissions import require_role
from .oauth_server import AuthorizeRequest, TokenRequest, RevokeRequest, authorize, exchange, consent_preview, revoke_client_tokens

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield

app = FastAPI(title="NEXUS AI Foundation", version="0.1.2-dev", lifespan=lifespan)
app.add_middleware(MCPBearerGuard)

@app.middleware("http")
async def reject_cross_origin_auth_writes(request: Request, call_next):
    if (request.url.path.startswith("/api/auth/") or request.url.path in ("/oauth/authorize", "/oauth/revoke")) and request.method in ("POST", "PUT", "PATCH", "DELETE"):
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
    return {"service": "nexus-ai", "version": "0.1.2-dev", "database": "connected" if database_ok() else "unavailable", "mcp": "protected", "security": "internal-token-only"}

@app.post("/api/auth/login")
def auth_login(payload: LoginRequest, response: Response):
    return login(payload, response)

@app.get("/api/auth/me")
def auth_me(request: Request):
    return current_user(request)

@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    return logout(request, response)

@app.get("/api/operator/overview")
def operator_overview(user: dict = Depends(require_role("owner", "operator", "viewer"))):
    return {"username": user["username"], "roles": user["roles"], "projects": "not-yet-enabled", "execution_enabled": False}

@app.get("/api/admin/overview")
def admin_overview(user: dict = Depends(require_role("owner"))):
    return {"username": user["username"], "management_enabled": False}

@app.get("/oauth/consent")
def oauth_consent(client_id: str, redirect_uri: str, request: Request):
    return consent_preview(client_id, redirect_uri, request)

@app.post("/oauth/revoke")
def oauth_revoke(payload: RevokeRequest, request: Request):
    return revoke_client_tokens(payload, request)

@app.post("/oauth/authorize")
def oauth_authorize(payload: AuthorizeRequest, request: Request):
    return authorize(payload, request)

@app.post("/oauth/token")
def oauth_token(payload: TokenRequest):
    return exchange(payload)

app.mount("/mcp", mcp.streamable_http_app())
