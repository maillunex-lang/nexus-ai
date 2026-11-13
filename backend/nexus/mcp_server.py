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
    """List implemented MCP tools and Director capabilities."""
    # Derived from the registry so the list can never drift from the real tools again.
    return {"tools": [tool.name for tool in mcp._tool_manager.list_tools()], "execution_enabled": False,
            "director": {"pipelines": True, "automatic_transitions": True, "change_sets": True,
                         "error_journal": True, "llm": False, "modifies_original_source": False}}

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

@mcp.tool()
def nexus_director_capabilities() -> dict:
    """Available rule-based workflows; no LLM or external AI API."""
    from .autonomous_director import capabilities
    return capabilities()


@mcp.tool()
def nexus_director_run(project_id: str, workflow: str = "validate_and_build_android") -> dict:
    """Run a deterministic owner-authorized project workflow asynchronously.

    Only explicitly build-enabled projects. Does not edit original source,
    invent code fixes, publish releases or invoke an AI API.
    """
    from .autonomous_director import run
    return run(project_id,workflow)


@mcp.tool()
def nexus_director_status(job_id: str) -> dict:
    """Read an owned autonomous workflow status, including failure or APK metadata."""
    from .autonomous_director import check
    return check(job_id)

@mcp.tool()
def nexus_director_create_project(project_id: str, title: str) -> dict:
    """Create a new Godot 4 starter project in an isolated NEXUS-owned directory.

    Owner write authorization required. No GitHub repository, VPS game service,
    APK, live deployment or arbitrary code execution is created automatically.
    Check progress using nexus_godot_registration_status.
    """
    from .godot_project_onboarding import request
    return request(project_id,"template",title)

@mcp.tool()
def nexus_director_workflows() -> dict:
    """List supported deterministic workflows and failure handling policies."""
    from .director_workflows import workflows
    return workflows()


@mcp.tool()
def nexus_director_launch(workflow: str, project_id: str, source: str = "") -> dict:
    """Launch a rule-based workflow: inspect, build APK, import GitHub/Lunex or create a starter.

    Requires owner write. All actions use existing bounded queues and isolated
    copies; no code modification, AI APIs or automatic publishing.
    """
    from .director_workflows import launch
    return launch(workflow,project_id,source)


@mcp.tool()
def nexus_director_task_status(director_job_id: str) -> dict:
    """Read current state and step of your rule-based director task."""
    from .director_workflows import inspect
    return inspect(director_job_id)


@mcp.tool()
def nexus_director_task_journal(director_job_id: str) -> dict:
    """Read up to 100 durable timestamped events for your director task."""
    from .director_workflows import journal
    return journal(director_job_id)

@mcp.tool()
def nexus_director_game_wizard_options() -> dict:
    """Available deterministic Godot game starter options. No AI API or cost."""
    return {"dimensions":["2d","3d"],
            "genres":["sandbox","survival","strategy","economy","platformer"],
            "platforms":["android","web","pc"],
            "controls":["touch","keyboard_mouse","gamepad"],
            "systems":["movement","camera","economy","inventory","day_night"],
            "note":"Generates a basic Godot 4 starter. Android/Web/PC are targets, not verified exports; touch and gamepad are metadata presets until their runtime input is implemented."}


@mcp.tool()
def nexus_director_game_wizard_create(project_id: str, title: str, dimension: str,
                                     genre: str, platforms: list[str],
                                     controls: str, systems: list[str]) -> dict:
    """Create a safe, isolated Godot 4 starter from the game wizard.

    Owner OAuth write required. Does not publish, create a GitHub repository,
    modify existing games, or automatically enable APK builds.
    """
    import json
    from .godot_project_onboarding import request
    return request(project_id,"wizard",json.dumps({"title":title,"dimension":dimension,
                   "genre":genre,"platforms":platforms,"controls":controls,
                   "systems":systems},ensure_ascii=False))

@mcp.tool()
def nexus_graphics_enhancer_catalog() -> dict:
    """List built-in renderer-aware graphics effects and quality profiles, without AI APIs."""
    from .graphics_enhancer import catalog
    return catalog()


@mcp.tool()
def nexus_graphics_enhancer_audit(project_id: str, profile: str = "balanced") -> dict:
    """Audit a Godot game's graphics without changing project files.

    Returns detected features, candidate improvements and mobile-friendly
    quality budget. Requires owner OAuth read/write; never applies effects.
    """
    from .graphics_enhancer import audit
    return audit(project_id,profile)

@mcp.tool()
def nexus_android_optimization_audit(project_id: str) -> dict:
    """Read-only scan of mobile Godot performance risks, without running a device."""
    from .android_optimizer import inspect
    return inspect(project_id)


@mcp.tool()
def nexus_android_graphics_presets() -> dict:
    """List mobile quality presets and actual vs planned features."""
    from .android_optimizer import presets
    return presets()

@mcp.tool()
def nexus_director_request_approval(project_id: str, action: str, description: str = "") -> dict:
    """Create an inert owner-approval request and return its direct HTTPS approval URL.

    Works with an MCP read token. Supported actions: inspect_project,
    build_android_debug (only build-enabled games). No code is executed
    until the owner approves in the NEXUS dashboard.
    """
    from .director_requests import propose
    return propose(project_id,action,description)


@mcp.tool()
def nexus_director_approval_status(request_id: str) -> dict:
    """Read the current state of an owner-scoped approval request."""
    from .director_requests import status
    return status(request_id)

# --- Autonomous AI Director 0.6: agents, change sets, pipelines, error journal ---

@mcp.tool()
def nexus_director_agents() -> dict:
    """List Director agent roles, the pipeline stages each one executes and your active tasks.

    Agents are deterministic rule executors, not language models.
    """
    from .director_pipelines import agents
    return agents()


@mcp.tool()
def nexus_director_pipelines() -> dict:
    """Catalog of multi-stage Director pipelines, their stages, agents and safety limits."""
    from .director_pipelines import catalog
    return catalog()


@mcp.tool()
def nexus_director_changeset_create(project_id: str, files: list[dict], description: str = "") -> dict:
    """Propose a safe code change of 1-8 operations on .gd/.gdshader/.tscn/.tres files.

    Modify: {"path", "expected_sha256", "content"} where expected_sha256 comes from
    nexus_godot_project_file and content is the full new file text.
    Create: {"action": "create", "path", "content"} for a path that does not exist.
    Delete: {"action": "delete", "path", "expected_sha256"}. Rename = delete + create.
    Returns per-file diffs
    and a static verification verdict (pass/warn/block). Stores an inert, immutable
    proposal only: no game file is written and nothing is executed.
    """
    from .director_changesets import create
    return create(project_id, files, description)


@mcp.tool()
def nexus_director_changeset_status(changeset_id: str) -> dict:
    """Re-check your change set against the current source: diffs, SHA pins, verification."""
    from .director_changesets import inspect
    return inspect(changeset_id)


@mcp.tool()
def nexus_director_pipeline_plan(pipeline: str, project_id: str, changeset_id: str = "") -> dict:
    """Dry run of a Director pipeline: exact stages, agents, effects and plan digest. Executes nothing."""
    from .director_pipelines import plan
    return plan(pipeline, project_id, changeset_id)


@mcp.tool()
def nexus_director_pipeline_launch(pipeline: str, project_id: str, changeset_id: str = "", task_id: str = "") -> dict:
    """Start a Director pipeline; stages then advance automatically.

    Requires owner OAuth mcp:write. With a read token use
    nexus_director_pipeline_request_approval instead. Changes are applied only to an
    isolated copy; originals are never modified and nothing is published.
    Optional task_id links the run to a Mission Control task's history.
    """
    from .director_pipelines import launch
    return launch(pipeline, project_id, changeset_id, "", task_id)


@mcp.tool()
def nexus_director_pipeline_request_approval(pipeline: str, project_id: str, changeset_id: str = "", description: str = "", task_id: str = "") -> dict:
    """Create an inert owner-approval request for an exact pipeline plan and return its approval URL.

    Works with an MCP read token. The owner reviews the stages and the code diff in
    the NEXUS dashboard; the pipeline starts only after that approval.
    """
    from .director_requests import propose_pipeline
    return propose_pipeline(pipeline, project_id, changeset_id, description, task_id)


@mcp.tool()
def nexus_director_pipeline_status(pipeline_id: str) -> dict:
    """Read your pipeline's state, stages and results. Also performs any due automatic transition."""
    from .director_pipelines import status
    return status(pipeline_id)


@mcp.tool()
def nexus_director_pipeline_journal(pipeline_id: str) -> dict:
    """Read up to 100 durable timestamped stage and transition events of your pipeline."""
    from .director_pipelines import journal
    return journal(pipeline_id)


@mcp.tool()
def nexus_director_pipeline_list(state: str = "", task_id: str = "") -> dict:
    """List your Director pipelines, optionally filtered by state (running, completed, failed, cancelled) or Mission Control task."""
    from .director_pipelines import list_pipelines
    return list_pipelines(state, task_id)


@mcp.tool()
def nexus_director_pipeline_cancel(pipeline_id: str) -> dict:
    """Stop further stages of your running pipeline. Requires owner OAuth mcp:write."""
    from .director_pipelines import cancel
    return cancel(pipeline_id)


@mcp.tool()
def nexus_director_pipeline_retry(pipeline_id: str) -> dict:
    """Retry the failed stage once, only for retryable failures. Requires owner OAuth mcp:write.

    Nothing is retried automatically; non-retryable failures need a corrected change set.
    """
    from .director_pipelines import retry
    return retry(pipeline_id)


@mcp.tool()
def nexus_director_error_log(limit: int = 20, project_id: str = "") -> dict:
    """Read your classified Director error journal: category, policy, Godot diagnostics, next action."""
    from .director_errors import list_errors
    return list_errors(limit, project_id)


@mcp.tool()
def nexus_director_changeset_patch(changeset_id: str) -> dict:
    """Export your change set as a git-compatible patch for manual `git apply`. Applies nothing."""
    from .director_adoption import patch
    return patch(changeset_id)


@mcp.tool()
def nexus_director_adoption_status() -> dict:
    """Show whether publishing validated change sets to a game's GitHub repository is configured."""
    from .director_adoption import describe
    return describe()


@mcp.tool()
def nexus_director_adoption_request(changeset_id: str, description: str = "") -> dict:
    """Request owner approval to publish a validated change set as a new nexus/ branch and draft PR.

    Works with an MCP read token and executes nothing. Requires a completed
    change_validate or change_build_apk pipeline for this change set. After the owner
    approves in the dashboard, one commit is created on a new branch; nothing is
    merged or deployed and no live game directory is touched.
    """
    from .director_requests import propose_adoption
    return propose_adoption(changeset_id, description)
