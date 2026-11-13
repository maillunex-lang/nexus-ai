import hashlib
import json
from contextlib import contextmanager
from unittest.mock import patch
import pytest
from nexus import director_changesets as c
from nexus import godot_job_queue, godot_projects
from nexus.mcp_principal import principal_var

OLD_A = "extends Node\n"
OLD_B = "extends Node2D\nfunc _ready():\n\tpass\n"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


@contextmanager
def env(tmp_path, scope="mcp:write", user="owner-1", project="basheco"):
    root = tmp_path / "game"
    if not root.exists():
        (root / "scripts").mkdir(parents=True)
        (root / "project.godot").write_text("[application]\n")
        (root / "scripts/a.gd").write_text(OLD_A)
        (root / "scripts/b.gd").write_text(OLD_B)
        (root / "main.tscn").write_text('[gd_scene format=3]\n[node name="Main" type="Node"]\n')
    queue = tmp_path / "queue"
    entries = {project: {"name": "Game", "root": str(root)}}
    token = principal_var.set({"user_id": user, "roles": ["owner"], "scope": scope})
    try:
        with patch.object(godot_projects, "_entries", return_value=entries), patch.object(c, "_entries", return_value=entries), \
             patch.object(c, "ROOT", queue / "director-changesets"), patch.object(c, "QUEUE", queue), \
             patch.object(godot_job_queue, "QUEUE", queue):
            yield root, queue
    finally:
        principal_var.reset(token)


def change(path, old, new):
    return {"path": path, "expected_sha256": sha(old), "content": new}


def test_read_scope_creates_inert_verified_changeset(tmp_path):
    with env(tmp_path, scope="mcp:read") as (root, queue):
        result = c.create("basheco", [change("scripts/a.gd", OLD_A, "extends Node\nvar speed = 3\n"),
                                      change("scripts/b.gd", OLD_B, OLD_B + "\nfunc jump():\n\tpass\n")], "Add speed")
        assert result["file_count"] == 2 and result["verification"]["verdict"] == "pass"
        assert result["ready_for_validation"] and result["applied"] is False
        assert "+var speed = 3" in result["files"][0]["diff"]
        assert (root / "scripts/a.gd").read_text() == OLD_A
        assert not (queue / "pending").exists()
        again = c.inspect(result["changeset_id"])
        assert again["digest"] == result["digest"] and len(result["digest"]) == 64
        record = c.load(result["changeset_id"], "owner-1")
        with pytest.raises(PermissionError):
            c.submit_validation(record)


def test_rejections(tmp_path):
    with env(tmp_path):
        good = change("scripts/a.gd", OLD_A, "extends Node\nvar x = 1\n")
        assert c.create("nope", [good])["error"] == "unknown_project"
        assert c.create("basheco", [])["error"] == "invalid_files"
        assert c.create("basheco", [{**good, "mode": "x"}])["error"] == "invalid_files"
        assert c.create("basheco", [good] * 2)["error"] == "duplicate_path"
        assert c.create("basheco", [good] * 9)["error"] == "invalid_files"
        assert c.create("basheco", [change("../x.gd", "", "x")])["error"] == "invalid_path"
        assert c.create("basheco", [change("scripts/new.gd", "", "extends Node\n")])["error"] == "not_found"
        stale = c.create("basheco", [change("scripts/a.gd", "old", "extends Node\nvar x = 1\n")])
        assert stale["error"] == "source_changed" and stale["current_sha256"] == sha(OLD_A)
        assert c.create("basheco", [change("scripts/a.gd", OLD_A, OLD_A)])["error"] == "no_changes"
        assert c.create("basheco", [change("scripts/a.gd", OLD_A, "x" * 100_001)])["error"] in ("changeset_too_large", "invalid_content")
        assert c.create("basheco", [good], "bad\x00text")["error"] == "invalid_description"
        with patch.object(c, "MAX_STORED", 0):
            assert c.create("basheco", [good])["error"] == "changeset_quota_exceeded"


def test_blocked_change_is_stored_but_never_queued(tmp_path):
    with env(tmp_path) as (root, queue):
        result = c.create("basheco", [change("scripts/a.gd", OLD_A, 'extends Node\nfunc a():\n\tOS.execute("sh", [])\n')])
        assert result["verification"]["verdict"] == "block" and not result["ready_for_validation"]
        submitted = c.submit_validation(c.load(result["changeset_id"], "owner-1"))
        assert submitted["error"] == "verification_blocked"
        assert not (queue / "pending").exists()


def test_scene_reference_resolves_inside_project(tmp_path):
    with env(tmp_path):
        scene = '[gd_scene format=3]\n[ext_resource type="Script" path="res://scripts/a.gd" id="1"]\n[ext_resource type="Script" path="res://scripts/zz.gd" id="2"]\n'
        result = c.create("basheco", [change("main.tscn", '[gd_scene format=3]\n[node name="Main" type="Node"]\n', scene)])
        assert [x["code"] for x in result["verification"]["checks"]] == ["missing_ext_resource"]
        assert result["verification"]["verdict"] == "warn" and result["ready_for_validation"]


def test_owner_isolation_and_tamper_detection(tmp_path):
    with env(tmp_path) as (root, queue):
        result = c.create("basheco", [change("scripts/a.gd", OLD_A, "extends Node\nvar x = 1\n")])
        identifier = result["changeset_id"]
    with env(tmp_path, user="owner-2"):
        assert c.inspect(identifier)["error"] == "changeset_not_found"
        assert c.inspect("cs-../../etc")["error"] == "changeset_not_found"
    with env(tmp_path) as (root, queue):
        path = queue / "director-changesets" / (identifier + ".json")
        data = json.loads(path.read_text())
        data["files"][0]["content"] = "extends Node\nvar x = 2\n"
        path.write_text(json.dumps(data))
        assert c.load(identifier, "owner-1") is None
        assert c.inspect(identifier)["error"] == "changeset_not_found"


def test_submit_single_file_uses_legacy_job_and_multi_file_uses_patches(tmp_path):
    with env(tmp_path) as (root, queue):
        one = c.create("basheco", [change("scripts/a.gd", OLD_A, "extends Node\nvar x = 1\n")])
        job = c.submit_validation(c.load(one["changeset_id"], "owner-1"))
        payload = json.loads((queue / "pending" / (job["job_id"] + ".json")).read_text())
        assert set(payload) == {"job_id", "project_id", "path", "expected_sha256", "content", "requested_by"}
        two = c.create("basheco", [change("scripts/a.gd", OLD_A, "extends Node\nvar x = 1\n"),
                                   change("scripts/b.gd", OLD_B, OLD_B + "var y = 2\n")])
        job = c.submit_validation(c.load(two["changeset_id"], "owner-1"))
        payload = json.loads((queue / "pending" / (job["job_id"] + ".json")).read_text())
        assert set(payload) == {"job_id", "project_id", "patches", "requested_by"}
        assert [p["path"] for p in payload["patches"]] == ["scripts/a.gd", "scripts/b.gd"]
        assert godot_job_queue.status(job["job_id"])["state"] == "pending"
        # Source changed after creation: the pin is re-checked at submission time.
        (root / "scripts/a.gd").write_text("extends Node\n# edited elsewhere\n")
        assert c.submit_validation(c.load(two["changeset_id"], "owner-1"))["error"] == "source_changed"
        assert c.inspect(two["changeset_id"])["stale"] is True


def test_validation_only_for_change_enabled_projects(tmp_path):
    with env(tmp_path, project="watermmo") as (root, queue):
        result = c.create("watermmo", [change("scripts/a.gd", OLD_A, "extends Node\nvar x = 1\n")])
        assert result["validation_enabled"] is False and result["ready_for_validation"] is False
        assert c.submit_validation(c.load(result["changeset_id"], "owner-1"))["error"] == "change_validation_not_enabled"


def test_create_delete_and_rename_operations(tmp_path):
    with env(tmp_path) as (root, queue):
        result = c.create("basheco", [
            {"action": "create", "path": "ui/hud.gd", "content": "extends Control\n"},
            {"action": "delete", "path": "scripts/b.gd", "expected_sha256": sha(OLD_B)},
            change("scripts/a.gd", OLD_A, "extends Node\nvar x = 1\n")], "rename b to hud")
        assert result["operations"] == {"modify": 1, "create": 1, "delete": 1} and result["verification"]["verdict"] == "pass"
        assert "+extends Control" in result["files"][0]["diff"] and "-extends Node2D" in result["files"][1]["diff"]
        assert not (root / "ui").exists() and (root / "scripts/b.gd").exists()
        job = c.submit_validation(c.load(result["changeset_id"], "owner-1"))
        patches = json.loads((queue / "pending" / (job["job_id"] + ".json")).read_text())["patches"]
        assert patches[0] == {"action": "create", "path": "ui/hud.gd", "content": "extends Control\n"}
        assert patches[1] == {"action": "delete", "path": "scripts/b.gd", "expected_sha256": sha(OLD_B)}
        assert set(patches[2]) == {"path", "expected_sha256", "content"}
        # A single create cannot use the legacy single-file job.
        one = c.create("basheco", [{"action": "create", "path": "ui/menu.gd", "content": "extends Control\n"}])
        job = c.submit_validation(c.load(one["changeset_id"], "owner-1"))
        assert "patches" in json.loads((queue / "pending" / (job["job_id"] + ".json")).read_text())
        # The file appeared in the source afterwards: the change set is stale.
        (root / "ui").mkdir()
        (root / "ui/menu.gd").write_text("extends Node\n")
        assert c.inspect(one["changeset_id"])["error"] == "already_exists"


def test_create_delete_rejections(tmp_path):
    with env(tmp_path) as (root, queue):
        for files, error in (
            ([{"action": "create", "path": "scripts/a.gd", "content": "x"}], "already_exists"),
            ([{"action": "create", "path": "scripts/a.gd/x.gd", "content": "x"}], "invalid_path"),
            ([{"action": "create", "path": "tool.sh", "content": "x"}], "unsupported_file_type"),
            ([{"action": "create", "path": ".godot/x.gd", "content": "x"}], "invalid_path"),
            ([{"action": "create", "path": "x.gd", "content": "x", "expected_sha256": "0" * 64}], "invalid_files"),
            ([{"action": "delete", "path": "scripts/a.gd", "expected_sha256": "0" * 64}], "source_changed"),
            ([{"action": "delete", "path": "scripts/none.gd", "expected_sha256": "0" * 64}], "not_found"),
            ([{"action": "delete", "path": "scripts/a.gd", "expected_sha256": sha(OLD_A), "content": ""}], "invalid_files"),
            ([{"action": "delete", "path": "project.godot", "expected_sha256": "0" * 64}], "unsupported_file_type"),
            ([{"action": "move", "path": "scripts/a.gd"}], "invalid_files"),
        ):
            assert c.create("basheco", files)["error"] == error, files
        blocked = c.create("basheco", [{"action": "create", "path": "x.gd", "content": 'func a():\n\tOS.execute("sh", [])\n'}])
        assert blocked["verification"]["verdict"] == "block"
        assert not (root / "x.gd").exists() and not (queue / "pending").exists()


def test_deleting_a_referenced_file_warns(tmp_path):
    with env(tmp_path) as (root, queue):
        (root / "main.tscn").write_text('[gd_scene format=3]\n[ext_resource type="Script" path="res://scripts/b.gd" id="1"]\n')
        result = c.create("basheco", [{"action": "delete", "path": "scripts/b.gd", "expected_sha256": sha(OLD_B)}])
        check = result["verification"]["checks"][0]
        assert check["code"] == "deleted_file_still_referenced" and "main.tscn" in check["message"]
        assert result["verification"]["verdict"] == "warn"
        fixed = c.create("basheco", [
            {"action": "delete", "path": "scripts/b.gd", "expected_sha256": sha(OLD_B)},
            change("main.tscn", (root / "main.tscn").read_text(), '[gd_scene format=3]\n[node name="Main" type="Node"]\n')])
        assert fixed["verification"]["verdict"] == "pass"


def test_records_written_before_actions_existed_still_load(tmp_path):
    with env(tmp_path) as (root, queue):
        result = c.create("basheco", [change("scripts/a.gd", OLD_A, "extends Node\nvar x = 1\n")])
        path = queue / "director-changesets" / (result["changeset_id"] + ".json")
        data = json.loads(path.read_text())
        del data["files"][0]["action"]
        path.write_text(json.dumps(data))
        assert c.inspect(result["changeset_id"])["digest"] == result["digest"]


def test_owner_enables_change_validation_per_project(tmp_path):
    from nexus import director_settings as s
    entries = {"basheco": {"name": "B"}, "watermmo": {"name": "W"}}
    with env(tmp_path, project="watermmo") as (root, queue), patch.object(s, "ROOT", queue / "director-settings"), \
         patch.object(s, "PROJECTS", entries):
        result = c.create("watermmo", [change("scripts/a.gd", OLD_A, "extends Node\nvar x = 1\n")])
        assert result["validation_enabled"] is False
        assert s.set_change_enabled("future-game", True)["error"] == "project_not_build_enabled"
        assert s.set_change_enabled("basheco", False)["error"] == "baseline_project_locked"
        assert s.set_change_enabled("watermmo", "yes")["error"] == "invalid_value"
        token = principal_var.set({"user_id": "owner-1", "roles": ["owner"], "scope": "mcp:read"})
        try:
            with pytest.raises(PermissionError):
                s.set_change_enabled("watermmo", True)
        finally:
            principal_var.reset(token)
        described = s.set_change_enabled("watermmo", True)
        assert [p["enabled"] for p in described["change_validation"]] == [True, True]
        assert c.inspect(result["changeset_id"])["ready_for_validation"] is True
        job = c.submit_validation(c.load(result["changeset_id"], "owner-1"))
        payload = json.loads((queue / "pending" / (job["job_id"] + ".json")).read_text())
        assert payload["project_id"] == "watermmo" and len(payload["patches"]) == 1
        s.set_change_enabled("watermmo", False)
        assert c.change_enabled() == ("basheco",)
        assert c.submit_validation(c.load(result["changeset_id"], "owner-1"))["error"] == "change_validation_not_enabled"
        assert len((queue / "director-settings" / "audit.jsonl").read_text().splitlines()) == 2
