from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException
from .mcp_server import mcp
from .db import database_ok
from .security import MCPBearerGuard
from .identity import LoginRequest, login, logout, current_user

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield

app = FastAPI(title="NEXUS AI Foundation", version="0.1.2-dev", lifespan=lifespan)
app.add_middleware(MCPBearerGuard)

@app.middleware("http")
async def reject_cross_origin_auth_writes(request: Request, call_next):
    if request.url.path.startswith("/api/auth/") and request.method in ("POST", "PUT", "PATCH", "DELETE"):
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

app.mount("/mcp", mcp.streamable_http_app())
