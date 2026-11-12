"""Temporary deny-by-default MCP gateway guard, NOT an OAuth implementation."""
import hmac
import os
from starlette.types import ASGIApp, Receive, Scope, Send


class MCPBearerGuard:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        secret = os.environ.get("NEXUS_MCP_INTERNAL_TOKEN", "")
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("latin1")
        expected = "Bearer " + secret
        if len(secret) < 32 or not hmac.compare_digest(authorization, expected):
            body = b'{"detail":"MCP authentication required"}'
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer"), (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
