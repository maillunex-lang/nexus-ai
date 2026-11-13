"""Bounded runtime benchmark and FPS-budget recipe on private project copies.

Run inside the existing flock-protected Godot worker. Project code executes only
in bubblewrap, with network disabled. Headless results are NOT device/GPU FPS.
"""
import hashlib
import math
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import tempfile
from godot_agent_workspace import run, source_manifest

PRESETS = {"economy": 30, "balanced": 45, "high": 60}
PATTERN = re.compile(r"perf-[a-f0-9]{32}\Z")


def fingerprint(root):
    root, files, _ = source_manifest(root)
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.relative_to(root).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(file.read_bytes()).digest())
    return digest.hexdigest()


def apply_recipe(workspace, preset):
    """Only trusted preset code; never accepts arbitrary source changes."""
    fps = PRESETS[preset]
    script = workspace / "nexus_perf_quality.gd"
    config = workspace / "project.godot"
    if script.exists() or "NexusPerfQuality" in config.read_text():
        raise ValueError("optimization_name_collision")
    script.write_text(f"extends Node\nfunc _ready() -> void:\n    Engine.max_fps = {fps}\n")
    text = config.read_text()
    line = 'NexusPerfQuality="*res://nexus_perf_quality.gd"\n'
    if re.search(r"(?m)^\[autoload\]\s*$", text):
        text = re.sub(r"(?m)^\[autoload\]\s*$", lambda m: m[0] + "\n" + line, text, count=1)
    else:
        text += "\n[autoload]\n" + line
    config.write_text(text)
    return {"recipe": "fps_budget", "preset": preset, "max_fps": fps,
            "changed_files": ["project.godot", script.name],
            "tradeoff": "Caps frame rate to reduce CPU work; does not prove faster rendering."}


def sandbox_command(workspace, executable):
    sandbox = shutil.which("bwrap")
    if not sandbox or not executable:
        raise ValueError("godot_or_bubblewrap_unavailable")
    cmd = [sandbox, "--die-with-parent", "--unshare-net", "--unshare-pid", "--unshare-user",
           "--uid", "0", "--gid", "0"]
    for path in ("/usr", "/lib", "/lib64", "/bin", "/opt/game-tools"):
        if Path(path).exists():
            cmd += ["--ro-bind", path, path]
    return cmd + ["--bind", str(workspace), "/workspace", "--tmpfs", "/tmp",
                  "--proc", "/proc", "--dev", "/dev", "--chdir", "/workspace",
                  str(Path(executable).resolve()), "--headless", "--path", "/workspace"]


def resource_limits():
    resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))


def benchmark(workspace, seconds, godot="godot"):
    probe = workspace / "nexus_perf_probe.gd"
    if probe.exists():
        raise ValueError("probe_name_collision")
    shutil.copyfile(Path(__file__).with_name("godot_performance_probe.gd"), probe)
    try:
        cmd = sandbox_command(workspace, shutil.which(godot))
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/workspace",
               "LANG": "C.UTF-8", "XDG_CACHE_HOME": "/tmp", "XDG_CONFIG_HOME": "/tmp"}
        # Regular files bound memory consumption even when the game logs heavily.
        with tempfile.TemporaryFile() as log:
            proc = subprocess.run(cmd + ["--script", "res://nexus_perf_probe.gd", "--", f"duration={seconds}"],
                                  stdout=log, stderr=log, timeout=seconds + 20, env=env, check=False, preexec_fn=resource_limits)
            log.seek(max(0, log.tell() - 100_000))
            output = log.read().decode("utf-8", "replace")
        if proc.returncode or re.search(r"(?m)^\s*(?:SCRIPT ERROR:|Parse Error:|ERROR:)", output):
            raise ValueError("runtime_failed")
        records = [json.loads(line[len("NEXUS_PERF:"):]) for line in output.splitlines()
                   if line.startswith("NEXUS_PERF:")]
        if len(records) != 1 or records[0].get("samples", 0) < 5:
            raise ValueError("missing_runtime_metrics")
        metrics = records[0]
        for key in ("samples", "elapsed_seconds", "frame_ms_p95", "process_ms_p95",
                    "fps_observed", "static_memory_peak_bytes", "nodes_peak"):
            value = metrics.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("invalid_runtime_metrics")
        return metrics
    finally:
        probe.unlink(missing_ok=True)


def execute(root, parent, seconds, preset=""):
    parent = Path(parent)
    if type(seconds) is not int or not 5 <= seconds <= 60 or (preset and preset not in PRESETS):
        raise ValueError("invalid_options")
    before_sha = fingerprint(root)
    validation = run(root, parent, timeout=120)
    if not validation["passed"] or validation.get("godot_script_errors", 0):
        raise ValueError("godot_validation_failed")
    baseline_workspace = Path(validation["workspace"])
    baseline = benchmark(baseline_workspace, seconds)
    result = {"baseline": baseline, "source_sha256": before_sha, "published": False,
              "workspace_job_id": validation["job_id"], "mode": "headless_runtime"}
    if preset:
        # Copy the baseline source, but discard imported/runtime state. The staging
        # root stays outside the workspace parent, as required by the validator.
        with tempfile.TemporaryDirectory(prefix="nexus-perf-staging-") as temporary:
            optimized_workspace = Path(temporary) / "source"
            shutil.copytree(baseline_workspace, optimized_workspace,
                            ignore=shutil.ignore_patterns(".godot", ".local", ".config", "nexus_godot_report.json"))
            result["optimization"] = apply_recipe(optimized_workspace, preset)
            validated = run(optimized_workspace, parent, timeout=120)
            if not validated["passed"] or validated.get("godot_script_errors", 0):
                raise ValueError("optimized_validation_failed")
            after = benchmark(Path(validated["workspace"]), seconds)
        result.update(optimized=after, optimized_workspace_job_id=validated["job_id"],
                      comparison={key: after[key] - baseline[key] for key in
                                  ("frame_ms_p95", "process_ms_p95", "static_memory_peak_bytes")},
                      conclusion="Measured deltas only; FPS cap is a quality/energy tradeoff, not a speedup claim.")
    if fingerprint(root) != before_sha:
        raise ValueError("source_changed_during_run")
    result["source_modified"] = False
    return result


def process_pending(base, workspaces, projects):
    for state in ("pending", "running", "completed", "failed"):
        (base / ("performance_" + state)).mkdir(parents=True, exist_ok=True)
    for file in sorted((base / "performance_pending").glob("perf-*.json"))[:1]:
        if not PATTERN.fullmatch(file.stem) or file.is_symlink() or file.stat().st_size > 4096:
            continue
        running = base / "performance_running" / file.name
        os.rename(file, running)
        data = {}
        try:
            data = json.loads(running.read_text())
            if (not isinstance(data, dict) or set(data) != {"job_id", "project_id", "seconds", "preset", "requested_by"}
                    or data["job_id"] != file.stem or data["project_id"] not in projects
                    or not isinstance(data["requested_by"], str) or not 1 <= len(data["requested_by"]) <= 128):
                raise ValueError("invalid_request")
            result = execute(projects[data["project_id"]], workspaces, data["seconds"], data["preset"])
            state = "completed"
        except Exception as exc:
            result = {"error": "performance_run_failed", "reason": str(exc) if isinstance(exc, ValueError) and re.fullmatch(r"[a-z_]{1,80}", str(exc)) else type(exc).__name__,
                      "source_modified_by_worker": False}
            state = "failed"
        destination = base / ("performance_" + state) / file.name
        # Queue execution is serialized by the existing host worker's flock.
        with destination.open("x") as handle:
            json.dump({"requested_by": data.get("requested_by") if isinstance(data, dict) else None,
                       "result": result}, handle)
        running.unlink()
