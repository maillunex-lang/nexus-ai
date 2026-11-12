from contextlib import asynccontextmanager
from fastapi import FastAPI
from .mcp_server import mcp
from .db import database_ok
from .security import MCPBearerGuard

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield

app = FastAPI(title="NEXUS AI Foundation", version="0.1.1-dev", lifespan=lifespan)
app.add_middleware(MCPBearerGuard)

@app.get("/api/health")
def health():
    return {"service": "nexus-ai", "status": "ok"}

@app.get("/api/status")
def status():
    return {"service": "nexus-ai", "version": "0.1.1-dev", "database": "connected" if database_ok() else "unavailable", "mcp": "protected", "security": "internal-token-only"}

app.mount("/mcp", mcp.streamable_http_app())
