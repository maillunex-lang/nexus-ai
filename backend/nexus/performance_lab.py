"""Owner-scoped Performance Lab queue. API never executes Godot or accepts paths."""
import re
import uuid
from .director_store import read, write_new
from .godot_job_queue import QUEUE
from .godot_projects import PROJECTS, _root
from .mcp_principal import require_owner, require_owner_write

JOB = re.compile(r"perf-[a-f0-9]{32}\Z")
PRESETS = {"economy": 30, "balanced": 45, "high": 60}


def submit(project_id: str, seconds: int = 10, preset: str = "") -> dict:
    owner = require_owner_write()
    # Imported snapshots are inspection-only until explicitly enabled by the operator.
    if project_id not in PROJECTS:
        return {"error": "project_not_execution_enabled"}
    if type(seconds) is not int or not 5 <= seconds <= 60:
        return {"error": "invalid_duration", "range_seconds": [5, 60]}
    if preset and preset not in PRESETS:
        return {"error": "unknown_preset", "presets": list(PRESETS)}
    try:
        _root(project_id)
    except ValueError:
        return {"error": "project_unavailable"}
    job = "perf-" + uuid.uuid4().hex
    record = {"job_id": job, "project_id": project_id, "seconds": seconds,
              "preset": preset, "requested_by": str(owner["user_id"])}
    write_new(QUEUE / "performance_pending" / (job + ".json"), record)
    return {"job_id": job, "state": "queued", "mode": "headless_runtime",
            "optimization": preset or None, "source_modified": False,
            "gpu_measured": False, "device_measured": False,
            "next_tool": "nexus_godot_profile_status"}


def status(job_id: str) -> dict:
    owner = require_owner()
    if not isinstance(job_id, str) or not JOB.fullmatch(job_id):
        return {"error": "invalid_job_id"}
    for state in ("completed", "failed", "running", "pending"):
        data = read(QUEUE / ("performance_" + state) / (job_id + ".json"), 100_000)
        if data is not None:
            if data.get("requested_by") != str(owner["user_id"]):
                return {"error": "not_found"}
            return {"job_id": job_id, "state": state, "result": data.get("result")}
    return {"error": "not_found"}
