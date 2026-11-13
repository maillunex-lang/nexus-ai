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
