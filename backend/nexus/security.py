"""Fail-closed bearer authentication for all MCP HTTP requests."""
import hmac
import os

from starlette.types import ASGIApp, Receive, Scope, Send

from .oauth_server import oauth_token_identity
from .mcp_principal import principal_var, resolve


def authorized_bearer(authorization: str) -> bool:
    if not authorization.startswith("Bearer "):
        return False
    token = authorization[7:]
    if not token or len(token) > 512:
        return False
    secret = os.environ.get("NEXUS_MCP_INTERNAL_TOKEN", "")
    # Internal bootstrap credential must never be accepted on a public issuer.
    internal_enabled = not os.environ.get("NEXUS_OAUTH_ISSUER")
    if internal_enabled and len(secret) >= 32 and hmac.compare_digest(token, secret):
        return True
    try:
        return oauth_token_identity(token)
    except Exception:
        # Database outage cannot grant access.
        return False


class MCPBearerGuard:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not (
            scope.get("path", "") == "/mcp" or scope.get("path", "").startswith("/mcp/")
        ):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("latin1")
        if not authorized_bearer(authorization):
            issuer = os.environ.get("NEXUS_OAUTH_ISSUER", "").rstrip("/")
            challenge = 'Bearer realm="nexus-mcp"'
            if issuer.startswith("https://"):
                challenge += ', resource_metadata="' + issuer + '/.well-known/oauth-protected-resource"'
            body = b'{"detail":"MCP authentication required"}'
            await send({"type": "http.response.start", "status": 401, "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", challenge.encode("ascii")),
                (b"cache-control", b"no-store"),
            ]})
            await send({"type": "http.response.body", "body": body})
            return
        # ContextVar is reset after each ASGI request to prevent identity leakage.
        principal = None
        try:
            principal = resolve(authorization)
        except Exception:
            principal = None
        token = principal_var.set(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            principal_var.reset(token)
