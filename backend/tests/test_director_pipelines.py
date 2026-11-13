import hashlib
import json
from contextlib import contextmanager
from unittest.mock import patch
import pytest
from nexus import director_changesets as c
from nexus import director_errors as e
from nexus import director_pipelines as p
from nexus import godot_build_queue, godot_job_queue, godot_one_command, godot_projects
from nexus import android_optimizer, graphics_enhancer
from nexus.mcp_principal import principal_var

OLD = "extends Node\n"
NEW = "extends Node\nvar speed = 3\n"
WORKSPACE = "godot-" + "c" * 32


@contextmanager
def env(tmp_path, scope="mcp:write", user="owner-1", preset=True):
    root = tmp_path / "game"
    if not root.exists():
        (root / "scripts").mkdir(parents=True)
        (root / "project.godot").write_text('[application]\nconfig/name="Game"\n')
        (root / "scripts/a.gd").write_text(OLD)
        (root / "scripts/b.gd").write_text(OLD)
        if preset:
            (root / "export_presets.cfg").write_text('[preset.0]\nname="Android"\nplatform="Android"\n')
    queue = tmp_path / "queue"
    entries = {"basheco": {"name": "Game", "root": str(root)},
               "future-game": {"name": "Future", "root": str(root), "inspection_only": True}}
    build_enabled = {"basheco": entries["basheco"]}
    token = principal_var.set({"user_id": user, "roles": ["owner"], "scope": scope})
    try:
        with patch.object(godot_projects, "_entries", return_value=entries), patch.object(c, "_entries", return_value=entries), \
             patch.object(p, "_entries", return_value=entries), patch.object(p, "PROJECTS", build_enabled), \
             patch.object(godot_one_command, "PROJECTS", build_enabled), \
             patch.object(c, "ROOT", queue / "director-changesets"), patch.object(c, "QUEUE", queue), \
             patch.object(p, "ROOT", queue / "director-pipelines"), patch.object(e, "ROOT", queue / "director-errors"), \
             patch.object(godot_job_queue, "QUEUE", queue), patch.object(godot_build_queue, "QUEUE", queue), \
             patch.object(godot_one_command, "QUEUE", queue):
            yield root, queue
    finally:
        principal_var.reset(token)


@contextmanager
def scope(value, user="owner-1"):
    token = principal_var.set({"user_id": user, "roles": ["owner"], "scope": value})
    try:
        yield
    finally:
        principal_var.reset(token)


def changeset(files=("scripts/a.gd",), content=NEW):
    return c.create("basheco", [{"path": f, "expected_sha256": hashlib.sha256(OLD.encode()).hexdigest(), "content": content} for f in files])


def host_finish(queue, source, target, job_id, result):
    """Simulate the separate host worker moving a job to its result folder."""
    data = json.loads((queue / source / (job_id + ".json")).read_text())
    (queue / source / (job_id + ".json")).unlink()
    (queue / target).mkdir(parents=True, exist_ok=True)
    (queue / target / (job_id + ".json")).write_text(json.dumps(
        {"job_id": job_id, "requested_by": data["requested_by"], "result": result}))


def stage(view, name):
    return next(s for s in view["stages"] if s["name"] == name)


def test_plan_is_dry_run_with_stable_digest(tmp_path):
    with env(tmp_path, scope="mcp:read") as (root, queue):
        first = p.plan("build_apk", "basheco")
        assert first["executed"] is False and [s["name"] for s in first["stages"]] == ["preflight", "build", "delivery"]
        assert [s["agent"] for s in first["stages"]] == ["tester", "devops", "director"]
        assert first["plan_digest"] == p.plan("build_apk", "basheco")["plan_digest"] != p.plan("project_audit", "basheco")["plan_digest"]
        assert first["effects"]["modifies_original_source"] is False and first["effects"]["publishes"] is False
        assert not (queue / "director-pipelines").exists()
        assert p.plan("shell", "basheco")["error"] == "unsupported_pipeline"
        assert p.plan("build_apk", "nope")["error"] == "unknown_project"
        assert p.plan("build_apk", "future-game")["error"] == "project_not_build_enabled"
        assert p.plan("build_apk", "basheco", "cs-" + "a" * 32)["error"] == "unexpected_changeset"
        assert p.plan("change_validate", "basheco")["error"] == "changeset_not_found"
        with pytest.raises(PermissionError):
            p.launch("build_apk", "basheco")
        with pytest.raises(PermissionError):
            p.cancel("pipe-" + "a" * 32)
        with pytest.raises(PermissionError):
            p.retry("pipe-" + "a" * 32)


def test_project_audit_runs_all_stages_automatically(tmp_path):
    with env(tmp_path) as (root, queue):
        with patch.object(p, "android_audit", wraps=android_optimizer.inspect), patch.object(p, "graphics_audit", wraps=graphics_enhancer.audit):
            view = p.launch("project_audit", "future-game")
        assert view["state"] == "completed" and view["progress"] == "4/4"
        assert view["result"]["inventory"]["counts"]["script"] == 2 and view["source_modified"] is False
        events = [x["event"] for x in p.journal(view["pipeline_id"])["events"]]
        assert events.count("transition") == 3 and events[0] == "created" and events[-1] == "pipeline_completed"
        assert not (queue / "build_pending").exists() and not (queue / "pending").exists()


def test_build_pipeline_transitions_on_poll_even_with_read_token(tmp_path):
    with env(tmp_path) as (root, queue):
        view = p.launch("build_apk", "basheco")
        assert view["state"] == "running" and view["current_stage"] == "build" and view["current_agent"] == "devops"
        assert stage(view, "preflight")["summary"]["android_preset"] is True
        job = stage(view, "build")["job_id"]
        assert json.loads((queue / "build_pending" / (job + ".json")).read_text())["kind"] == "auto_android_debug_build"
        assert p.status(view["pipeline_id"])["current_stage"] == "build"
        assert len(list((queue / "build_pending").iterdir())) == 1  # polling never re-queues
        host_finish(queue, "build_pending", "build_completed", job,
                    {"passed": True, "bytes": 123, "sha256": "d" * 64, "workspace_job_id": WORKSPACE})
        with scope("mcp:read"):
            done = p.status(view["pipeline_id"])
        assert done["state"] == "completed" and done["progress"] == "3/3"
        assert done["result"] == {"build_job_id": job, "sha256": "d" * 64, "bytes": 123,
                                  "next_tool": "nexus_godot_apk_download_link", "published": False, "includes_changeset": False}
        assert done["next_tool"] == "nexus_godot_apk_download_link"
        assert p.list_pipelines("completed")["pipelines"][0]["pipeline_id"] == view["pipeline_id"]


def test_preflight_stops_before_queueing_a_doomed_build(tmp_path):
    with env(tmp_path, preset=False) as (root, queue):
        view = p.launch("build_apk", "basheco")
        assert view["state"] == "failed" and view["failure"]["category"] == "android_preset_unavailable"
        assert view["failure"]["retryable"] is False and "nexus_director_pipeline_retry" not in view["next_tools"]
        assert not (queue / "build_pending").exists()
        assert p.retry(view["pipeline_id"])["error"] == "retry_not_allowed"
        log = e.list_errors()
        assert log["errors"][0]["stage"] == "preflight" and log["errors"][0]["reference"] == view["pipeline_id"]
        assert log["errors"][0]["agent"] == "tester"


def test_change_build_pipeline_end_to_end(tmp_path):
    with env(tmp_path) as (root, queue):
        cs = changeset(("scripts/a.gd", "scripts/b.gd"))
        planned = p.plan("change_build_apk", "basheco", cs["changeset_id"])
        view = p.launch("change_build_apk", "basheco", cs["changeset_id"], planned["plan_digest"])
        assert view["current_stage"] == "validate_change" and view["current_agent"] == "developer"
        assert stage(view, "verify_change")["summary"]["verdict"] == "pass"
        validation = stage(view, "validate_change")["job_id"]
        assert len(json.loads((queue / "pending" / (validation + ".json")).read_text())["patches"]) == 2
        host_finish(queue, "pending", "completed", validation,
                    {"passed": True, "workspace_job_id": WORKSPACE, "godot_exit_code": 0})
        view = p.status(view["pipeline_id"])
        assert view["current_stage"] == "build_validated"
        build = stage(view, "build_validated")["job_id"]
        request = json.loads((queue / "build_pending" / (build + ".json")).read_text())
        assert request["validation_job_id"] == validation and request["workspace_job_id"] == WORKSPACE
        host_finish(queue, "build_pending", "build_completed", build,
                    {"passed": True, "bytes": 5, "sha256": "e" * 64, "workspace_job_id": WORKSPACE})
        done = p.status(view["pipeline_id"])
        assert done["state"] == "completed" and done["result"]["includes_changeset"] is True
        assert (root / "scripts/a.gd").read_text() == OLD and (root / "scripts/b.gd").read_text() == OLD


def test_godot_failure_is_classified_journaled_and_not_retried(tmp_path):
    log = 'SCRIPT ERROR: Parse Error: Unexpected token\n   at: GDScript::reload (res://scripts/a.gd:2)\n'
    with env(tmp_path) as (root, queue):
        cs = changeset()
        view = p.launch("change_validate", "basheco", cs["changeset_id"])
        job = stage(view, "validate_change")["job_id"]
        host_finish(queue, "pending", "failed", job, {"passed": False, "godot_output": log})
        failed = p.status(view["pipeline_id"])
        assert failed["state"] == "failed" and failed["failure"]["category"] == "godot_validation_failed"
        assert failed["failure"]["auto_retry"] is False and failed["failure"]["policy"] == "stop_and_report"
        assert stage(failed, "validate_change")["diagnostics"][0] == {
            "kind": "script_error", "message": "Parse Error: Unexpected token", "file": "scripts/a.gd", "line": 2}
        assert stage(failed, "change_report")["state"] == "pending"
        assert p.status(view["pipeline_id"])["state"] == "failed"
        assert len(e.list_errors()["errors"]) == 1  # recorded once, not on every poll
        assert p.retry(view["pipeline_id"])["error"] == "retry_not_allowed"
        assert len(list((queue / "pending").iterdir())) == 0


def test_blocked_or_stale_change_never_reaches_host_queue(tmp_path):
    with env(tmp_path) as (root, queue):
        blocked = changeset(content='extends Node\nfunc a():\n\tOS.execute("sh", [])\n')
        view = p.launch("change_validate", "basheco", blocked["changeset_id"])
        assert view["state"] == "failed" and view["failure"]["category"] == "verification_blocked"
        stale = changeset()
        (root / "scripts/a.gd").write_text("extends Node\n# changed\n")
        view = p.launch("change_validate", "basheco", stale["changeset_id"])
        assert view["failure"]["category"] == "source_changed"
        assert not (queue / "pending").exists()


def test_timeout_then_bounded_explicit_retry(tmp_path):
    with env(tmp_path) as (root, queue):
        view = p.launch("build_apk", "basheco")
        with patch.object(p, "_now", return_value=p._now() + p.STAGE_TIMEOUT_SECONDS + 5):
            failed = p.status(view["pipeline_id"])
        assert failed["failure"]["category"] == "worker_timeout" and "nexus_director_pipeline_retry" in failed["next_tools"]
        again = p.retry(view["pipeline_id"])
        assert again["state"] == "running" and stage(again, "build")["attempts"] == 2
        assert stage(again, "build")["job_id"] != stage(view, "build")["job_id"]
        with patch.object(p, "_now", return_value=p._now() + p.STAGE_TIMEOUT_SECONDS + 5):
            p.status(view["pipeline_id"])
        assert p.retry(view["pipeline_id"])["error"] == "retry_not_allowed"
        assert len(list((queue / "build_pending").iterdir())) == 2


def test_missing_job_tolerated_briefly_then_fails(tmp_path):
    with env(tmp_path) as (root, queue):
        view = p.launch("build_apk", "basheco")
        job = stage(view, "build")["job_id"]
        hidden = (queue / "build_pending" / (job + ".json")).rename(queue / "hidden.json")
        assert p.status(view["pipeline_id"])["state"] == "running"
        hidden.rename(queue / "build_pending" / (job + ".json"))
        assert p.status(view["pipeline_id"])["state"] == "running"
        (queue / "build_pending" / (job + ".json")).unlink()
        states = [p.status(view["pipeline_id"])["state"] for _ in range(p.MAX_STATUS_MISSES)]
        assert states[-1] == "failed" and states[0] == "running"
        assert p.status(view["pipeline_id"])["failure"]["category"] == "job_unavailable"


def test_cancel_stops_transitions(tmp_path):
    with env(tmp_path) as (root, queue):
        view = p.launch("build_apk", "basheco")
        job = stage(view, "build")["job_id"]
        cancelled = p.cancel(view["pipeline_id"])
        assert cancelled["state"] == "cancelled" and cancelled["host_job_in_flight"] is True
        host_finish(queue, "build_pending", "build_completed", job, {"passed": True, "bytes": 1, "sha256": "f" * 64})
        assert p.status(view["pipeline_id"])["state"] == "cancelled"
        assert p.cancel(view["pipeline_id"])["error"] == "pipeline_not_running"
        assert p.retry(view["pipeline_id"])["error"] == "pipeline_not_failed"


def test_owner_isolation_limits_and_digest_pinning(tmp_path):
    with env(tmp_path) as (root, queue):
        assert p.launch("build_apk", "basheco", "", "0" * 64)["error"] == "plan_digest_mismatch"
        views = [p.launch("build_apk", "basheco") for _ in range(p.MAX_ACTIVE_PER_OWNER)]
        assert p.launch("build_apk", "basheco")["error"] == "too_many_active_pipelines"
        assert p.agents()["active_pipelines"] == p.MAX_ACTIVE_PER_OWNER
        devops = next(a for a in p.agents()["agents"] if a["id"] == "devops")
        assert devops["status"] == "active" and len(devops["active_tasks"]) == p.MAX_ACTIVE_PER_OWNER and devops["model_used"] is False
        identifier = views[0]["pipeline_id"]
        with scope("mcp:write", "owner-2"):
            assert p.status(identifier)["error"] == "pipeline_not_found"
            assert p.journal(identifier)["error"] == "pipeline_not_found"
            assert p.cancel(identifier)["error"] == "pipeline_not_found"
            assert p.list_pipelines()["pipelines"] == []
        assert p.status("pipe-../x")["error"] == "pipeline_not_found"
        path = queue / "director-pipelines" / (identifier + ".json")
        record = json.loads(path.read_text())
        record["project_id"] = "future-game"
        path.write_text(json.dumps(record))
        tampered = p.status(identifier)
        assert tampered["state"] == "failed" and tampered["failure"]["error"] == "plan_digest_mismatch"


def test_tick_advances_without_a_caller_and_lock_prevents_double_start(tmp_path):
    with env(tmp_path) as (root, queue):
        view = p.launch("build_apk", "basheco")
        job = stage(view, "build")["job_id"]
        host_finish(queue, "build_pending", "build_completed", job, {"passed": True, "bytes": 1, "sha256": "a" * 64})
        lock = queue / "director-pipelines" / "locks" / (view["pipeline_id"] + ".lock")
        lock.write_text("")
        with scope("mcp:read"):
            assert p.status(view["pipeline_id"])["state"] == "running"  # held lock: read only
        lock.unlink()
        token = principal_var.set(None)
        try:
            assert p.tick() == {"examined": 1, "advanced": 1}
            assert p.tick() == {"examined": 0, "advanced": 0}
        finally:
            principal_var.reset(token)
        assert p.status(view["pipeline_id"])["state"] == "completed"


def test_catalog_declares_safety_properties(tmp_path):
    with env(tmp_path, scope="mcp:read"):
        catalog = p.catalog()
        assert set(catalog["pipelines"]) == {"project_audit", "build_apk", "change_validate", "change_build_apk"}
        assert catalog["automatic_transitions"] is True
        assert not any(catalog[k] for k in ("automatic_retry", "automatic_code_fix", "automatic_publish", "modifies_original_source", "external_ai_api"))
        assert all(s in p.START for spec in p.PIPELINES.values() for s in spec["stages"])
    with pytest.raises(PermissionError):
        p.catalog()
