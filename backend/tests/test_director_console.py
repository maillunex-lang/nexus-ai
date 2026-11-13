import asyncio
from unittest.mock import patch
from fastapi.testclient import TestClient
from nexus import dashboard_director, director_requests
from nexus.main import app
from nexus.mcp_principal import principal_var
from nexus.mcp_server import mcp
from test_director_pipelines import env

NEW_TOOLS = {"nexus_director_agents", "nexus_director_pipelines", "nexus_director_changeset_create",
             "nexus_director_changeset_status", "nexus_director_pipeline_plan", "nexus_director_pipeline_launch",
             "nexus_director_pipeline_request_approval", "nexus_director_pipeline_status",
             "nexus_director_pipeline_journal", "nexus_director_pipeline_list", "nexus_director_pipeline_cancel",
             "nexus_director_pipeline_retry", "nexus_director_error_log"}
EXISTING_TOOLS = {"nexus_status", "nexus_capabilities", "nexus_agents", "nexus_godot_build_project",
                  "nexus_godot_apk_download_link", "nexus_director_run", "nexus_director_status",
                  "nexus_director_launch", "nexus_director_task_status", "nexus_director_request_approval",
                  "nexus_director_approval_status", "nexus_meshy_dispatch_preview", "nexus_godot_validate_change"}


def tool(name, **arguments):
    return asyncio.run(mcp._tool_manager.call_tool(name, arguments))


def test_new_tools_registered_and_existing_tools_preserved():
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert NEW_TOOLS <= names and EXISTING_TOOLS <= names
    assert set(tool("nexus_capabilities")["tools"]) == names


def test_mcp_tools_require_owner_and_respect_scopes(tmp_path):
    for name, arguments in (("nexus_director_pipelines", {}), ("nexus_director_agents", {}),
                            ("nexus_director_error_log", {}), ("nexus_director_pipeline_list", {}),
                            ("nexus_director_pipeline_status", {"pipeline_id": "pipe-" + "a" * 32})):
        try:
            tool(name, **arguments)
        except Exception as exc:
            assert "Owner OAuth authorization required" in str(exc)
        else:
            raise AssertionError(name + " must require an owner principal")
    with env(tmp_path, scope="mcp:read") as (root, queue), patch.object(director_requests, "ROOT", queue / "director-requests"):
        assert tool("nexus_director_pipeline_plan", pipeline="build_apk", project_id="basheco")["executed"] is False
        try:
            tool("nexus_director_pipeline_launch", pipeline="build_apk", project_id="basheco")
        except Exception as exc:
            assert "write scope" in str(exc)
        else:
            raise AssertionError("read token must not launch")
        proposal = tool("nexus_director_pipeline_request_approval", pipeline="build_apk", project_id="basheco")
        assert proposal["status"] == "pending" and not (queue / "build_pending").exists()
    with env(tmp_path, scope="mcp:write") as (root, queue):
        launched = tool("nexus_director_pipeline_launch", pipeline="build_apk", project_id="basheco")
        assert launched["current_stage"] == "build"
        assert tool("nexus_director_pipeline_cancel", pipeline_id=launched["pipeline_id"])["state"] == "cancelled"


def test_console_requires_owner_session(tmp_path):
    client = TestClient(app)
    for path in ("/api/director/pipelines", "/api/director/errors", "/api/director/agents", "/api/director/catalog"):
        assert client.get(path).status_code == 401
    assert client.post("/api/director/pipelines", json={"pipeline": "build_apk", "project_id": "basheco"}).status_code == 401
    with patch.object(dashboard_director, "current_user", return_value={"id": "u", "roles": ["operator"]}):
        assert client.get("/api/director/pipelines").status_code == 403
        assert client.post("/api/director/pipelines/pipe-" + "a" * 32 + "/cancel").status_code == 403


def test_console_owner_flow_and_csrf(tmp_path):
    client = TestClient(app)
    with env(tmp_path) as (root, queue), patch.object(dashboard_director, "current_user", return_value={"id": "owner-1", "roles": ["owner"]}):
        token = principal_var.set(None)
        try:
            blocked = client.post("/api/director/pipelines", json={"pipeline": "build_apk", "project_id": "basheco"},
                                  headers={"sec-fetch-site": "cross-site"})
            assert blocked.status_code == 403 and not (queue / "director-pipelines").exists()
            assert client.post("/api/director/pipelines", json={"pipeline": "build_apk", "project_id": "basheco"},
                               headers={"origin": "https://evil.example"}).status_code == 403
            launched = client.post("/api/director/pipelines", json={"pipeline": "build_apk", "project_id": "basheco"})
            assert launched.status_code == 202
            identifier = launched.json()["pipeline_id"]
            assert client.get("/api/director/pipelines").json()["pipelines"][0]["pipeline_id"] == identifier
            assert client.get("/api/director/pipelines/" + identifier).json()["current_stage"] == "build"
            assert client.get("/api/director/pipelines/" + identifier + "/journal").json()["events"][0]["event"] == "created"
            assert client.get("/api/director/agents").json()["active_pipelines"] == 1
            assert client.post("/api/director/pipelines/" + identifier + "/cancel").json()["state"] == "cancelled"
            assert client.post("/api/director/pipelines/" + identifier + "/retry").json()["error"] == "pipeline_not_failed"
            assert client.get("/api/director/errors").json()["errors"] == []
            assert client.get("/api/director/errors?limit=1000").json()["error"] == "invalid_limit"
            assert client.get("/api/director/pipelines/unknown").json()["error"] == "pipeline_not_found"
        finally:
            principal_var.reset(token)
