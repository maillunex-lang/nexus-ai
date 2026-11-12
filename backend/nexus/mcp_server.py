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
    return {"tools": ["nexus_status", "nexus_capabilities", "nexus_agents", "nexus_workflow", "nexus_godot_inspect_script", "nexus_godot_inspect_shader", "nexus_godot_projects", "nexus_godot_project_report", "nexus_godot_project_file", "nexus_github_repositories", "nexus_github_repository", "nexus_github_tree", "nexus_github_file", "nexus_github_change_preview", "nexus_github_branch_policy", "nexus_meshy_status", "nexus_meshy_text_to_3d_preview", "nexus_meshy_my_requests", "nexus_meshy_request_status", "nexus_meshy_prepare_request", "nexus_meshy_prepare_refine", "nexus_godot_gltf_mobile_audit"], "execution_enabled": False}

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

@mcp.tool()
def nexus_meshy_status() -> dict:
    """Check whether optional Meshy API integration is configured, without exposing private billing or API keys."""
    from .meshy_reader import connection_status
    return connection_status()

@mcp.tool()
def nexus_meshy_text_to_3d_preview(prompt: str, art_style: str = "realistic", mode: str = "preview") -> dict:
    """Preview a Meshy text-to-3D request and approval requirements. Does NOT generate a model, use credits, or call Meshy."""
    from .meshy_proposals import preview_text_to_3d
    return preview_text_to_3d(prompt, art_style, mode)

@mcp.tool()
def nexus_meshy_my_requests() -> dict:
    """List only the current OAuth owner's Meshy requests; no paid actions."""
    from .mcp_principal import require_owner
    from .db import connection
    principal = require_owner()
    with connection() as conn:
        rows = conn.execute("""SELECT id,status,dispatch_state,max_credits,provider_task_id
          FROM meshy_requests WHERE created_by=%s ORDER BY created_at DESC LIMIT 25""",
          (principal["user_id"],)).fetchall()
    return {"requests":[{"id":str(r[0]),"approval":r[1],"dispatch":r[2],
             "max_credits":r[3],"task_id":r[4]} for r in rows], "read_only":True}


@mcp.tool()
def nexus_meshy_request_status(request_id: str) -> dict:
    """Read one owned request and Meshy progress, never disclose signed download URLs."""
    from uuid import UUID
    from .mcp_principal import require_owner
    from .db import connection
    from .meshy_reader import task_status
    principal = require_owner()
    try:
        identifier = UUID(request_id)
    except (ValueError, TypeError, AttributeError):
        return {"error":"invalid_request_id"}
    with connection() as conn:
        row = conn.execute("""SELECT status,dispatch_state,provider_task_id FROM meshy_requests
          WHERE id=%s AND created_by=%s""",(identifier,principal["user_id"])).fetchone()
    if not row:
        return {"error":"request_not_found"}
    result = {"id":str(identifier),"approval":row[0],"dispatch":row[1],"task_id":row[2]}
    if row[2]:
        result["provider"] = task_status(row[2])
    return result

@mcp.tool()
def nexus_meshy_prepare_request(prompt: str, max_credits: int = 20, art_style: str = "realistic") -> dict:
    """Prepare a Meshy request for the authenticated owner. NEVER charges credits.

    Requires a separate explicit approval in the NEXUS AI dashboard.
    """
    from psycopg.types.json import Jsonb
    from .mcp_principal import require_owner
    from .db import connection
    from .meshy_proposals import preview_text_to_3d
    principal = require_owner()
    if type(max_credits) is not int or not 1 <= max_credits <= 1000:
        return {"error":"invalid_credit_ceiling"}
    preview = preview_text_to_3d(prompt, art_style, "preview")
    if "error" in preview:
        return preview
    with connection() as conn:
        row = conn.execute("""INSERT INTO meshy_requests
          (created_by,proposal_sha256,proposal,max_credits)
          VALUES (%s,%s,%s,%s) RETURNING id,expires_at""",
          (principal["user_id"],preview["proposal_sha256"],
           Jsonb(preview["proposal"]),max_credits)).fetchone()
        conn.execute("""INSERT INTO meshy_request_events(request_id,actor_id,action)
          VALUES (%s,%s,'created')""",(row[0],principal["user_id"]))
    return {"request_id":str(row[0]),"status":"pending","max_credits":max_credits,
            "expires_at":row[1].isoformat(),"approval_required":True,
            "generation_started":False,"credits_spent":0,
            "next_step":"Approve the exact request in the NEXUS AI dashboard; approval alone does not dispatch."}

@mcp.tool()
def nexus_meshy_prepare_refine(preview_request_id: str, max_credits: int = 10) -> dict:
    """Create separate non-billable texture approval request for completed owned Preview."""
    from uuid import UUID
    from .mcp_principal import require_owner
    from .db import connection
    from .meshy_reader import task_status
    principal=require_owner()
    try:
        identifier=UUID(preview_request_id)
    except (ValueError,TypeError,AttributeError):
        return {"error":"invalid_preview_request_id"}
    if type(max_credits) is not int or not 10 <= max_credits <= 1000:
        return {"error":"invalid_credit_ceiling"}
    with connection() as conn:
        row=conn.execute("""SELECT provider_task_id,dispatch_state FROM meshy_requests
          WHERE id=%s AND created_by=%s""",(identifier,principal["user_id"])).fetchone()
    if not row or row[1]!="submitted" or not row[0]:
        return {"error":"preview_not_submitted_or_not_owned"}
    if task_status(row[0]).get("task",{}).get("status")!="SUCCEEDED":
        return {"error":"preview_not_completed"}
    with connection() as conn:
        result=conn.execute("""INSERT INTO meshy_refine_requests
          (preview_request_id,created_by,max_credits) VALUES (%s,%s,%s)
          ON CONFLICT (preview_request_id) DO NOTHING RETURNING id,expires_at""",
          (identifier,principal["user_id"],max_credits)).fetchone()
    if not result:
        return {"error":"refine_request_already_exists"}
    return {"request_id":str(result[0]),"status":"pending","expires_at":result[1].isoformat(),
            "max_credits":max_credits,"generation_started":False,
            "next_step":"Approve separately in the authenticated NEXUS dashboard."}


@mcp.tool()
def nexus_godot_gltf_mobile_audit(gltf_json: dict) -> dict:
    """Audit glTF 2.0 JSON metadata for Android suitability, without modifying files."""
    from .godot_glb_audit import assess_gltf
    return assess_gltf(gltf_json)
