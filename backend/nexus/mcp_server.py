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
    return {"tools": ["nexus_status", "nexus_capabilities", "nexus_agents", "nexus_workflow", "nexus_godot_inspect_script", "nexus_godot_inspect_shader", "nexus_godot_projects", "nexus_godot_project_report", "nexus_godot_project_file", "nexus_github_repositories", "nexus_github_repository", "nexus_github_tree", "nexus_github_file", "nexus_github_change_preview", "nexus_github_branch_policy", "nexus_meshy_status", "nexus_meshy_text_to_3d_preview", "nexus_meshy_my_requests", "nexus_meshy_request_status", "nexus_meshy_prepare_request", "nexus_meshy_prepare_refine", "nexus_godot_gltf_mobile_audit", "nexus_meshy_review_request", "nexus_meshy_review_refine", "nexus_meshy_dispatch_readiness", "nexus_meshy_dispatch_preview", "nexus_meshy_dispatch_refine", "nexus_meshy_refine_status", "nexus_godot_change_preview", "nexus_godot_workspace_report", "nexus_godot_validate_change", "nexus_godot_validation_status", "nexus_godot_build_android", "nexus_godot_build_status", "nexus_godot_apk_download_link", "nexus_godot_build_project", "nexus_godot_register_project", "nexus_godot_registration_status"], "execution_enabled": False}

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

@mcp.tool()
def nexus_meshy_review_request(request_id: str, decision: str) -> dict:
    """Explicit owner OAuth write approval or rejection. NEVER starts paid generation."""
    from uuid import UUID
    from .mcp_principal import require_owner_write
    from .db import connection
    principal=require_owner_write()
    if decision not in ("approve","reject"):
        return {"error":"invalid_decision"}
    try:
        identifier=UUID(request_id)
    except (ValueError,TypeError,AttributeError):
        return {"error":"invalid_request_id"}
    with connection() as conn:
        with conn.transaction():
            row=conn.execute("""SELECT status,expires_at,proposal,max_credits FROM meshy_requests
              WHERE id=%s AND created_by=%s FOR UPDATE""",
              (identifier,principal["user_id"])).fetchone()
            if not row:
                return {"error":"request_not_found"}
            if row[0]!="pending" or row[1].timestamp()<=__import__("time").time():
                return {"error":"already_reviewed_or_expired"}
            status="approved" if decision=="approve" else "rejected"
            conn.execute("""UPDATE meshy_requests SET status=%s,
              approved_by=%s,approved_at=CASE WHEN %s='approved' THEN now() ELSE NULL END
              WHERE id=%s""",(status,principal["user_id"] if status=="approved" else None,
              status,identifier))
            conn.execute("""INSERT INTO meshy_request_events(request_id,actor_id,action)
              VALUES (%s,%s,%s)""",(identifier,principal["user_id"],status))
    return {"request_id":str(identifier),"status":status,
            "max_credits":row[3],"proposal":row[2],
            "generation_started":False,"credits_spent":0,
            "next_step":"Separate explicit dispatch required to incur any credits."}

@mcp.tool()
def nexus_meshy_review_refine(request_id: str, decision: str) -> dict:
    """Owner-only write-scope approval for texture Refine. No credits spent."""
    from uuid import UUID
    from .mcp_principal import require_owner_write
    from .db import connection
    principal=require_owner_write()
    if decision not in ("approve","reject"):
        return {"error":"invalid_decision"}
    try:
        identifier=UUID(request_id)
    except (ValueError,TypeError,AttributeError):
        return {"error":"invalid_request_id"}
    with connection() as conn:
        with conn.transaction():
            row=conn.execute("""SELECT status,expires_at,max_credits FROM meshy_refine_requests
              WHERE id=%s AND created_by=%s FOR UPDATE""",
              (identifier,principal["user_id"])).fetchone()
            if not row:
                return {"error":"request_not_found"}
            if row[0]!="pending" or row[1].timestamp()<=__import__("time").time():
                return {"error":"already_reviewed_or_expired"}
            status="approved" if decision=="approve" else "rejected"
            conn.execute("""UPDATE meshy_refine_requests SET status=%s,
              approved_at=CASE WHEN %s='approved' THEN now() ELSE NULL END WHERE id=%s""",
              (status,status,identifier))
    return {"request_id":str(identifier),"status":status,"max_credits":row[2],
            "generation_started":False,"credits_spent":0,
            "dispatch_enabled":False}


@mcp.tool()
def nexus_meshy_dispatch_readiness(request_id: str) -> dict:
    """Check owner request and billing safeguards. Never sends a paid provider request."""
    import os
    from uuid import UUID
    from .mcp_principal import require_owner
    from .db import connection
    from .meshy_dispatch import PREVIEW_COST
    principal=require_owner()
    try:
        identifier=UUID(request_id)
    except (ValueError,TypeError,AttributeError):
        return {"error":"invalid_request_id"}
    with connection() as conn:
        row=conn.execute("""SELECT status,dispatch_state,max_credits,expires_at,proposal
          FROM meshy_requests WHERE id=%s AND created_by=%s""",
          (identifier,principal["user_id"])).fetchone()
    if not row:
        return {"error":"request_not_found"}
    verified=os.environ.get("NEXUS_MESHY_VERIFIED_PREVIEW_COST")==str(PREVIEW_COST)
    ready=(row[0]=="approved" and row[1]=="not_started" and
           row[2]>=PREVIEW_COST and row[3].timestamp()>__import__("time").time()
           and row[4].get("mode")=="preview" and verified)
    return {"request_id":str(identifier),"approved":row[0]=="approved",
            "dispatch_state":row[1],"max_credits":row[2],
            "provider_cost_verified":verified,"estimated_cost_credits":PREVIEW_COST,
            "ready":ready,"generation_started":False,"credits_spent":0,
            "note":"This is a dry-run readiness check, never a dispatch."}

@mcp.tool()
def nexus_meshy_dispatch_preview(request_id: str, confirmation: str) -> dict:
    """Paid Preview dispatch. Requires owner mcp:write and exact confirmation 'DISPATCH <request_id>'.
    
    Charges provider credits only when operator separately enabled verified pricing.
    No automatic retries. Do not call without user approval of this exact request.
    """
    from uuid import UUID
    from fastapi import HTTPException
    from .mcp_principal import require_owner_write
    from .meshy_dispatch import dispatch
    principal=require_owner_write()
    try:
        identifier=UUID(request_id)
    except (ValueError,TypeError,AttributeError):
        return {"error":"invalid_request_id"}
    if confirmation!="DISPATCH "+str(identifier):
        return {"error":"explicit_dispatch_confirmation_required",
                "required_confirmation":"DISPATCH "+str(identifier)}
    try:
        return dispatch(identifier,None,owner_id=principal["user_id"])
    except HTTPException as exc:
        return {"error":"dispatch_rejected","status_code":exc.status_code,"reason":exc.detail}


@mcp.tool()
def nexus_meshy_dispatch_refine(request_id: str, confirmation: str) -> dict:
    """Paid Refine dispatch. Owner mcp:write, explicit exact request confirmation, no retries.

    Do not invoke without user's separate approval for this request and 10 credits.
    """
    from uuid import UUID
    from fastapi import HTTPException
    from .mcp_principal import require_owner_write
    from .meshy_refine_dispatch import dispatch
    principal=require_owner_write()
    try:
        identifier=UUID(request_id)
    except (ValueError,TypeError,AttributeError):
        return {"error":"invalid_request_id"}
    if confirmation!="DISPATCH "+str(identifier):
        return {"error":"explicit_dispatch_confirmation_required",
                "required_confirmation":"DISPATCH "+str(identifier)}
    try:
        return dispatch(identifier,None,owner_id=principal["user_id"])
    except HTTPException as exc:
        return {"error":"dispatch_rejected","status_code":exc.status_code,"reason":exc.detail}


@mcp.tool()
def nexus_meshy_refine_status(request_id: str) -> dict:
    """Read owned Refine dispatch state and sanitized provider task status."""
    from uuid import UUID
    from .mcp_principal import require_owner
    from .db import connection
    from .meshy_reader import task_status
    principal=require_owner()
    try:
        identifier=UUID(request_id)
    except (ValueError,TypeError,AttributeError):
        return {"error":"invalid_request_id"}
    with connection() as conn:
        row=conn.execute("""SELECT status,dispatch_state,provider_task_id,max_credits
          FROM meshy_refine_requests WHERE id=%s AND created_by=%s""",
          (identifier,principal["user_id"])).fetchone()
    if not row:
        return {"error":"request_not_found"}
    result={"request_id":str(identifier),"approval_status":row[0],
            "dispatch_state":row[1],"max_credits":row[3]}
    if row[2]:
        result["provider"]=task_status(row[2])
    return result

@mcp.tool()
def nexus_godot_change_preview(project_id: str, relative_path: str, expected_sha256: str, proposed_content: str) -> dict:
    """Preview a proposed Godot scene/script/shader/resource change without writing to the game.

    Exact SHA-256 guards against stale source. Returns bounded diff and static findings.
    """
    from .godot_change_preview import preview
    return preview(project_id,relative_path,expected_sha256,proposed_content)

@mcp.tool()
def nexus_godot_workspace_report(job_id: str) -> dict:
    """Read an isolated Godot validation report by exact job ID. Never runs or modifies a game."""
    from .godot_workspace_reports import report
    return report(job_id)

@mcp.tool()
def nexus_godot_validate_change(project_id: str, relative_path: str, expected_sha256: str, proposed_content: str) -> dict:
    """Queue SHA-pinned Godot change validation in an isolated copy, never original.

    Owner OAuth mcp:write is required. Runs asynchronously via separate sandboxed
    host worker. Use nexus_godot_validation_status with returned job_id.
    """
    from .godot_job_queue import submit
    return submit(project_id,relative_path,expected_sha256,proposed_content)


@mcp.tool()
def nexus_godot_validation_status(job_id: str) -> dict:
    """Check an owned isolated Godot change-validation job by ID."""
    from .godot_job_queue import status
    return status(job_id)

@mcp.tool()
def nexus_godot_build_android(validation_job_id: str) -> dict:
    """Queue a debug APK build from your successfully validated Godot change job.

    Requires owner OAuth mcp:write; no original modification or publishing.
    """
    from .godot_build_queue import submit
    return submit(validation_job_id)


@mcp.tool()
def nexus_godot_build_status(build_job_id: str) -> dict:
    """Get the status, SHA-256 and size of your Android debug APK build."""
    from .godot_build_queue import status
    return status(build_job_id)

@mcp.tool()
def nexus_godot_apk_download_link(build_job_id: str) -> dict:
    """Issue a private five-minute download URL for your completed Android debug APK."""
    from .godot_apk_delivery import issue
    return issue(build_job_id)

@mcp.tool()
def nexus_godot_build_project(project_id: str = "basheco") -> dict:
    """One command: safely copy an allowlisted Godot project, validate, build debug APK.

    Requires owner OAuth mcp:write. Poll nexus_godot_build_status with job_id;
    once completed, call nexus_godot_apk_download_link. No source edits or publish.
    """
    from .godot_one_command import start
    return start(project_id)

@mcp.tool()
def nexus_godot_register_project(project_id: str, source_type: str, source: str) -> dict:
    """Register a Godot project from public GitHub or a permitted Lunex directory.

    Owner OAuth write required. Creates an inspection-only snapshot; does not
    automatically authorize builds or execute untrusted project code.
    """
    from .godot_project_onboarding import request
    return request(project_id,source_type,source)


@mcp.tool()
def nexus_godot_registration_status(job_id: str) -> dict:
    """Read your Godot project registration job result."""
    from .godot_project_onboarding import status
    return status(job_id)

@mcp.tool()
def nexus_godot_registered_projects() -> dict:
    """List your newly imported inspection-only Godot projects."""
    from .godot_project_onboarding import list_registered
    return list_registered()
