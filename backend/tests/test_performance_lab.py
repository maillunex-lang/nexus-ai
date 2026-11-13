import hashlib
import json
from pathlib import Path
import subprocess
import pytest
from nexus import performance_lab as lab
from nexus.mcp_principal import principal_var
import godot_performance_worker as worker


@pytest.fixture
def owner():
    token = principal_var.set({"user_id": "alice", "roles": ["owner"], "scope": "mcp:write"})
    yield
    principal_var.reset(token)


def test_queue_ownership_and_inspection_gate(tmp_path, monkeypatch, owner):
    monkeypatch.setattr(lab, "QUEUE", tmp_path)
    monkeypatch.setattr(lab, "_root", lambda _: tmp_path)
    assert lab.submit("imported")["error"] == "project_not_execution_enabled"
    assert lab.submit("basheco", 100)["error"] == "invalid_duration"
    assert lab.submit("basheco", preset="ultra")["error"] == "unknown_preset"
    job = lab.submit("basheco", 5, "economy")["job_id"]
    assert lab.status(job)["state"] == "pending"
    principal_var.set({"user_id": "bob", "roles": ["owner"], "scope": "mcp:read"})
    assert lab.status(job) == {"error": "not_found"}
    assert lab.status("../../etc/passwd")["error"] == "invalid_job_id"
    with pytest.raises(PermissionError):
        lab.submit("basheco")


def test_recipe_preserves_settings_and_source(tmp_path):
    root = tmp_path / "original"
    copy = tmp_path / "copy"
    root.mkdir(); copy.mkdir()
    text = '[application]\nconfig/name="Test"\n[autoload]\nExisting="*res://existing.gd"\n'
    (root / "project.godot").write_text(text)
    (copy / "project.godot").write_text(text)
    worker.apply_recipe(copy, "economy")
    assert (root / "project.godot").read_text() == text
    assert 'Existing="*res://existing.gd"' in (copy / "project.godot").read_text()
    assert "Engine.max_fps = 30" in (copy / "nexus_perf_quality.gd").read_text()
    with pytest.raises(ValueError, match="collision"):
        worker.apply_recipe(copy, "high")


def test_execute_compares_real_results_and_guards_original(tmp_path, monkeypatch):
    root = tmp_path / "source"; root.mkdir()
    parent = tmp_path / "workspaces"; parent.mkdir()
    (root / "project.godot").write_text('[application]\nconfig/name="Test"\n')
    original = worker.fingerprint(root)
    calls = []
    def validate(source, destination, timeout):
        import shutil
        workspace = destination / str(len(calls))
        calls.append(workspace)
        shutil.copytree(source, workspace)
        return {"passed": True, "workspace": str(workspace), "job_id": str(len(calls))}
    monkeypatch.setattr(worker, "run", validate)
    def benchmark(workspace, seconds):
        value = 20 if (workspace / "nexus_perf_quality.gd").exists() else 10
        return {"frame_ms_p95": value, "process_ms_p95": 1,
                "static_memory_peak_bytes": 1024, "gpu_measured": False}
    monkeypatch.setattr(worker, "benchmark", benchmark)
    result = worker.execute(root, parent, 5, "economy")
    assert result["comparison"]["frame_ms_p95"] == 10
    assert result["source_modified"] is False
    assert worker.fingerprint(root) == original


def test_worker_failures_owner_and_duration(tmp_path, monkeypatch):
    pending = tmp_path / "performance_pending"; pending.mkdir()
    job = "perf-" + "a" * 32
    (pending / (job + ".json")).write_text(json.dumps({"job_id": job, "project_id": "bad",
        "requested_by": "alice", "seconds": 5, "preset": ""}))
    monkeypatch.setattr(worker, "execute", lambda *args: pytest.fail("must not execute"))
    worker.process_pending(tmp_path, tmp_path, {})
    record = json.loads((tmp_path / "performance_failed" / (job + ".json")).read_text())
    assert record["requested_by"] == "alice"
    assert record["result"]["error"] == "performance_run_failed"


def test_timeout_removes_probe(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "sandbox_command", lambda *args: ["godot"])
    def timeout(*a, **kw):
        raise subprocess.TimeoutExpired("godot", 5)
    monkeypatch.setattr(worker.subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        worker.benchmark(tmp_path, 5)
    assert not (tmp_path / "nexus_perf_probe.gd").exists()


def test_mcp_tools_are_registered():
    from nexus.mcp_server import mcp
    names = {tool.name for tool in mcp._tool_manager.list_tools()}
    assert {"nexus_godot_profile_start", "nexus_godot_profile_status",
            "nexus_godot_optimize_isolated"} <= names


def test_runtime_errors_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "sandbox_command", lambda *args: ["godot"])
    def broken(*a, **kw):
        kw["stdout"].write(b'SCRIPT ERROR: broken scene\n')
        return subprocess.CompletedProcess([], 0)
    monkeypatch.setattr(worker.subprocess, "run", broken)
    with pytest.raises(ValueError, match="runtime_failed"):
        worker.benchmark(tmp_path, 5)
    assert not (tmp_path / "nexus_perf_probe.gd").exists()
