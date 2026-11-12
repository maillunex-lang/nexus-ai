from mcp.server.fastmcp import FastMCP
from .db import database_ok

mcp = FastMCP("NEXUS AI", stateless_http=True, json_response=True)

@mcp.tool()
def nexus_status() -> dict:
    """Read the status of the NEXUS AI foundation service."""
    return {"service": "nexus-ai", "version": "0.1.0-dev", "database": "connected" if database_ok() else "unavailable"}

@mcp.tool()
def nexus_capabilities() -> dict:
    """List implemented read-only capabilities."""
    return {"tools": ["nexus_status", "nexus_capabilities"], "execution_enabled": False}
