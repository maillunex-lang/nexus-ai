from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from .db import database_ok

# Mounting under /mcp in FastAPI requires the ASGI app's internal path to be /.
mcp = FastMCP("NEXUS AI", stateless_http=True, json_response=True, streamable_http_path="/", transport_security=TransportSecuritySettings(allowed_hosts=["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "api", "api:*", "rikagro.ru"], allowed_origins=["http://localhost:*", "http://127.0.0.1:*", "https://rikagro.ru"]))

@mcp.tool()
def nexus_status() -> dict:
    """Read the status of the NEXUS AI foundation service."""
    return {"service": "nexus-ai", "version": "0.1.6-dev", "database": "connected" if database_ok() else "unavailable"}

@mcp.tool()
def nexus_capabilities() -> dict:
    """List implemented read-only capabilities."""
    return {"tools": ["nexus_status", "nexus_capabilities", "nexus_agents", "nexus_workflow", "nexus_godot_inspect_script", "nexus_godot_inspect_shader", "nexus_godot_projects", "nexus_godot_project_report", "nexus_godot_project_file", "nexus_github_repositories", "nexus_github_repository", "nexus_github_tree", "nexus_github_file", "nexus_github_change_preview", "nexus_github_branch_policy"], "execution_enabled": False}

@mcp.tool()
def nexus_agents() -> dict:
    """List the planned NEXUS AI agent roles, without starting any executor."""
    from .agents import AGENTS
    return {"agents":[{**a,"status":"planned","execution_enabled":False} for a in AGENTS],
            "execution_enabled":False}

@mcp.tool()
def nexus_workflow() -> dict:
    """Describe Mission Control workflows and safety limits; no private task data."""
    return {"mission_control":"available via authenticated web dashboard",
            "operations":["create_project","create_task","assign_agent","change_status","draft_director_plan"],
            "mcp_mutations_enabled":False,"remote_execution_enabled":False,
            "note":"MCP write tools require future per-user token authorization and explicit approvals."}

@mcp.tool()
def nexus_godot_inspect_script(source: str, filename: str = "script.gd") -> dict:
    """Statically inspect supplied Godot 4 GDScript text for potential performance and lifecycle issues. No file access or execution."""
    from .godot_inspector import inspect_gdscript
    return inspect_gdscript(source,filename)

@mcp.tool()
def nexus_godot_inspect_shader(source: str, filename: str = "effect.gdshader") -> dict:
    """Statically inspect supplied Godot shader text for mobile performance risks. No file access or execution."""
    from .godot_inspector import inspect_shader
    return inspect_shader(source,filename)

@mcp.tool()
def nexus_godot_projects() -> dict:
    """List only explicitly registered Godot projects; no arbitrary host paths."""
    from .godot_projects import list_projects
    return list_projects()

@mcp.tool()
def nexus_godot_project_report(project_id: str = "basheco", include_files: bool = False) -> dict:
    """Read-only static inventory and bounded analysis of a registered Godot project."""
    from .godot_projects import inspect_project
    return inspect_project(project_id,include_files)

@mcp.tool()
def nexus_godot_project_file(project_id: str, relative_path: str) -> dict:
    """Read-only static analysis of a single .gd/.gdshader/.tscn/.tres or project.godot file, with strict path checks."""
    from .godot_projects import inspect_file
    return inspect_file(project_id,relative_path)

@mcp.tool()
def nexus_github_repositories() -> dict:
    """List explicitly approved public GitHub repositories. No credentials or writes."""
    from .github_reader import list_repositories
    return list_repositories()

@mcp.tool()
def nexus_github_repository(repo_id: str = "nexus-ai") -> dict:
    """Get public repository metadata and immutable default branch HEAD SHA."""
    from .github_reader import repository_head
    return repository_head(repo_id)

@mcp.tool()
def nexus_github_tree(repo_id: str, commit_sha: str) -> dict:
    """Read a bounded repository tree at a full immutable 40-character commit SHA."""
    from .github_reader import repository_tree
    return repository_tree(repo_id, commit_sha)

@mcp.tool()
def nexus_github_file(repo_id: str, commit_sha: str, path: str) -> dict:
    """Read bounded UTF-8 source from an allowlisted public repo at immutable commit SHA."""
    from .github_reader import repository_file
    return repository_file(repo_id, commit_sha, path)

@mcp.tool()
def nexus_github_change_preview(repo_id: str, base_sha: str, path: str, proposed_content: str, branch: str) -> dict:
    """Preview an exact proposed file change as a bounded diff. Does not write, run tests or create PRs."""
    from .github_proposals import preview_change
    return preview_change(repo_id, base_sha, path, proposed_content, branch)

@mcp.tool()
def nexus_github_branch_policy() -> dict:
    """Read safety requirements for future approval-gated branch and draft PR creation. No writes."""
    from .github_proposals import branch_policy
    return branch_policy()
