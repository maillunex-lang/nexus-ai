import json
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from nexus import director_pipelines as p
from nexus import director_requests as d
from nexus.mcp_principal import principal_var
from test_director_pipelines import env, changeset, host_finish, stage, scope, OLD

OWNER = {"id": "owner-1", "roles": ["owner"]}


def test_read_token_proposes_pipeline_and_owner_session_launches_it(tmp_path):
    with env(tmp_path, scope="mcp:read") as (root, queue), patch.object(d, "ROOT", queue / "director-requests"):
        cs = changeset()
        proposal = d.propose_pipeline("change_build_apk", "basheco", cs["changeset_id"], "Speed tweak")
        assert proposal["status"] == "pending" and proposal["executed"] is False
        assert proposal["approval_url"].endswith(proposal["request_id"])
        assert proposal["stages"] == ["verify_change", "validate_change", "build_validated", "delivery"]
        assert not (queue / "director-pipelines").exists() and not (queue / "pending").exists()
        assert d.status(proposal["request_id"])["plan_current"] is True
        token = principal_var.set(None)  # browser session: no MCP principal at all
        try:
            with patch.object(d, "current_user", return_value={"id": "viewer", "roles": ["viewer"]}):
                with pytest.raises(HTTPException) as err:
                    d.review(proposal["request_id"], "approved", None)
                assert err.value.status_code == 403
            with patch.object(d, "current_user", return_value=OWNER):
                detail = d.get(proposal["request_id"], None)
                assert "+var speed = 3" in detail["changeset"]["files"][0]["diff"]
                assert [s["name"] for s in detail["plan"]["stages"]] == proposal["stages"]
                approved = d.review(proposal["request_id"], "approved", None)
                assert approved["status"] == "queued" and approved["pipeline_state"]["current_stage"] == "validate_change"
                with pytest.raises(HTTPException) as err:
                    d.review(proposal["request_id"], "approved", None)
                assert err.value.status_code == 409
                stored = json.loads((queue / "director-requests" / (proposal["request_id"] + ".json")).read_text())
                assert "changeset" not in stored and "pipeline_state" not in stored
                job = stage(approved["pipeline_state"], "validate_change")["job_id"]
                host_finish(queue, "pending", "completed", job, {"passed": True, "workspace_job_id": "godot-" + "c" * 32})
                assert d.get(proposal["request_id"], None)["pipeline_state"]["current_stage"] == "build_validated"
        finally:
            principal_var.reset(token)
        assert len(list((queue / "director-pipelines").glob("pipe-*.json"))) == 1
        assert (root / "scripts/a.gd").read_text() == OLD


def test_denied_request_launches_nothing(tmp_path):
    with env(tmp_path, scope="mcp:read") as (root, queue), patch.object(d, "ROOT", queue / "director-requests"):
        proposal = d.propose_pipeline("build_apk", "basheco")
        with patch.object(d, "current_user", return_value=OWNER):
            assert d.review(proposal["request_id"], "denied", None)["status"] == "denied"
        assert not (queue / "director-pipelines").exists() and not (queue / "build_pending").exists()


def test_invalid_proposals_and_tampered_plan(tmp_path):
    with env(tmp_path, scope="mcp:read") as (root, queue), patch.object(d, "ROOT", queue / "director-requests"):
        assert d.propose_pipeline("shell", "basheco")["error"] == "unsupported_pipeline"
        assert d.propose_pipeline("build_apk", "future-game")["error"] == "project_not_build_enabled"
        assert d.propose_pipeline("change_validate", "basheco", "cs-" + "0" * 32)["error"] == "changeset_not_found"
        assert d.propose_pipeline("build_apk", "basheco", "", "x\x00")["error"] == "invalid_description"
        proposal = d.propose_pipeline("build_apk", "basheco")
        path = queue / "director-requests" / (proposal["request_id"] + ".json")
        record = json.loads(path.read_text())
        record["pipeline"] = "project_audit"  # swapped after the proposal was shown
        path.write_text(json.dumps(record))
        with patch.object(d, "current_user", return_value=OWNER):
            assert d.get(proposal["request_id"], None)["plan_current"] is False
            result = d.review(proposal["request_id"], "approved", None)
        assert result["status"] == "failed" and result["result"]["error"] == "plan_digest_mismatch"
        assert not (queue / "director-pipelines").exists()


def test_session_owner_can_read_live_build_state_without_mcp_principal(tmp_path):
    """Regression: the dashboard detail endpoint raised PermissionError for queued builds."""
    with env(tmp_path, scope="mcp:read") as (root, queue), patch.object(d, "ROOT", queue / "director-requests"), \
         patch.object(d, "_entries", return_value={"basheco": {"name": "Game"}}):
        proposal = d.propose("basheco", "build_android_debug")
        token = principal_var.set(None)
        try:
            with patch.object(d, "current_user", return_value=OWNER):
                approved = d.review(proposal["request_id"], "approved", None)
                assert approved["status"] == "queued"
                assert d.get(proposal["request_id"], None)["build"]["state"] == "pending"
        finally:
            principal_var.reset(token)
