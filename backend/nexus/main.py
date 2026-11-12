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
from .identity import LoginRequest, login, logout, current_user
from .permissions import require_role
from .oauth_server import AuthorizeRequest, TokenRequest, RevokeRequest, authorize, exchange, consent_preview, revoke_client_tokens

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield

app = FastAPI(title="NEXUS AI Foundation", version="0.1.4-dev", lifespan=lifespan)
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
    return {"service": "nexus-ai", "version": "0.1.4-dev", "database": "connected" if database_ok() else "unavailable", "mcp": "protected", "security": "internal-token-only"}

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

@app.get("/oauth/authorize")
def oauth_authorize_browser(request: Request):
    # The browser opens a same-origin SPA consent screen; no approval on GET.
    from urllib.parse import urlencode
    return RedirectResponse("/?" + urlencode([("oauth", "1"), *request.query_params.multi_items()]), status_code=303)

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
    return exchange(payload)


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
