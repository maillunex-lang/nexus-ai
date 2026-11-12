"""Request-local OAuth principal for MCP tool calls."""
from contextvars import ContextVar
from .oauth_server import oauth_token_principal

principal_var: ContextVar[dict | None] = ContextVar("nexus_mcp_principal", default=None)

def require_owner() -> dict:
    principal = principal_var.get()
    if not principal or "owner" not in principal.get("roles", []) or principal.get("scope") != "mcp:read":
        raise PermissionError("Owner OAuth authorization required")
    return principal

def resolve(authorization: str) -> dict | None:
    if not authorization.startswith("Bearer "):
        return None
    return oauth_token_principal(authorization[7:])
