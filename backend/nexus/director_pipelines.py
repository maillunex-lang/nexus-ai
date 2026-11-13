"""Autonomous AI Director: durable multi-stage pipelines with automatic transitions.

A pipeline is a fixed, typed sequence of stages. Each stage belongs to one agent
role and is executed by an existing bounded capability (static inspection, the
verification gate, the isolated Godot validation queue, the Android debug build
queue). The Director starts the next stage by itself as soon as the previous
one succeeds, stops on the first failure, classifies it and writes it to the
owner's error journal.

Deterministic rules only: no LLM, no shell, no network, no writes to original
game sources, no publishing, no automatic retries. The whole plan is authorized
once (owner write scope or an owner-approved request) and pinned by a SHA-256
digest that is re-checked before every transition; later status polls, even
with a read token, can therefore only continue exactly what was approved.
"""
import hashlib
import json
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from . import director_changesets as changesets
from . import director_errors as errors
from . import director_store as store
from .agents import AGENTS
from .android_optimizer import inspect as android_audit
from .godot_build_queue import status as build_status, submit as build_validated
from .godot_job_queue import QUEUE, status as validation_status
from .godot_one_command import start as build_project
from .godot_projects import PROJECTS, _entries, _root, inspect_project
from .graphics_enhancer import audit as graphics_audit
from .mcp_principal import principal_var, require_owner, require_owner_write

ROOT = QUEUE / "director-pipelines"
ID = re.compile(r"pipe-[0-9a-f]{32}\Z")
PROJECT = re.compile(r"[a-z][a-z0-9-]{2,39}\Z")
STAGE_TIMEOUT_SECONDS = 45 * 60
MAX_ACTIVE_PER_OWNER = 3
MAX_STAGE_ATTEMPTS = 2
MAX_STATUS_MISSES = 3
MAX_RECORD_BYTES = 80_000
MAX_LISTED = 50
MAX_SCANNED = 400
MAX_JOURNAL = 100

STAGES = {
    "inventory": ("tester", "Статическая инвентаризация проекта"),
    "android_audit": ("artist", "Аудит мобильной производительности"),
    "graphics_audit": ("artist", "Аудит графики"),
    "audit_report": ("director", "Сводный отчёт аудита"),
    "preflight": ("tester", "Проверка готовности к сборке (проект, пресет Android)"),
    "build": ("devops", "Изолированная копия, проверка Godot и сборка debug APK"),
    "verify_change": ("tester", "Статическая проверка набора изменений и SHA-256"),
    "validate_change": ("developer", "Применение изменений к изолированной копии и проверка Godot"),
    "build_validated": ("devops", "Сборка debug APK из проверенной копии"),
    "change_report": ("director", "Отчёт о проверке изменений"),
    "delivery": ("director", "Контрольная сумма APK и готовность к выдаче ссылки"),
}
PIPELINES = {
    "project_audit": {
        "description": "Инвентаризация -> аудит Android -> аудит графики -> отчёт. Только чтение.",
        "stages": ["inventory", "android_audit", "graphics_audit", "audit_report"],
        "changeset": False, "builds": False},
    "build_apk": {
        "description": "Предпроверка -> изолированная сборка debug APK -> выдача.",
        "stages": ["preflight", "build", "delivery"],
        "changeset": False, "builds": True},
    "change_validate": {
        "description": "Проверка набора изменений -> Godot в изолированной копии -> отчёт.",
        "stages": ["verify_change", "validate_change", "change_report"],
        "changeset": True, "builds": False},
    "change_build_apk": {
        "description": "Проверка изменений -> Godot в изолированной копии -> debug APK с изменениями -> выдача.",
        "stages": ["verify_change", "validate_change", "build_validated", "delivery"],
        "changeset": True, "builds": True},
}


def _now() -> float:
    return time.time()


@contextmanager
def _as_owner(record: dict):
    """Run pre-authorized stage work as the pipeline owner.

    Safe because the plan was authorized with owner write scope at launch and
    its digest is verified before any stage runs.
    """
    token = principal_var.set({"user_id": record["owner"], "roles": ["owner"], "scope": "mcp:write"})
    try:
        yield
    finally:
        principal_var.reset(token)


def _digest(pipeline: str, project_id: str, changeset_id: str, changeset_digest: str) -> str:
    canonical = json.dumps({"pipeline": pipeline, "project_id": project_id, "changeset_id": changeset_id,
                            "changeset_digest": changeset_digest, "stages": PIPELINES[pipeline]["stages"]},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _plan(owner_id: str, pipeline: str, project_id: str, changeset_id: str) -> dict:
    if not isinstance(pipeline, str) or pipeline not in PIPELINES:
        return {"error": "unsupported_pipeline", "supported": sorted(PIPELINES)}
    spec = PIPELINES[pipeline]
    if not isinstance(project_id, str) or not PROJECT.fullmatch(project_id) or project_id not in _entries():
        return {"error": "unknown_project"}
    if not isinstance(changeset_id, str):
        return {"error": "invalid_changeset_id"}
    changeset_digest = ""
    if spec["changeset"]:
        record = changesets.load(changeset_id, owner_id)
        if record is None:
            return {"error": "changeset_not_found"}
        if record["project_id"] != project_id:
            return {"error": "changeset_project_mismatch"}
        if project_id not in changesets.change_enabled():
            return {"error": "change_validation_not_enabled", "enabled_projects": list(changesets.change_enabled())}
        changeset_digest = record["digest"]
    elif changeset_id:
        return {"error": "unexpected_changeset"}
    if spec["builds"] and project_id not in PROJECTS:
        return {"error": "project_not_build_enabled", "build_enabled_projects": sorted(PROJECTS)}
    return {"pipeline": pipeline, "project_id": project_id, "description": spec["description"],
            "changeset_id": changeset_id, "changeset_digest": changeset_digest,
            "stages": [{"name": name, "agent": STAGES[name][0], "description": STAGES[name][1]} for name in spec["stages"]],
            "plan_digest": _digest(pipeline, project_id, changeset_id, changeset_digest),
            "effects": {"modifies_original_source": False, "builds_debug_apk": spec["builds"],
                        "publishes": False, "uses_ai_model": False, "automatic_transitions": True,
                        "automatic_retry": False}}


def plan(pipeline: str, project_id: str, changeset_id: str = "") -> dict:
    """Dry run: the exact plan and digest that launch or approval would execute."""
    owner = require_owner()
    result = _plan(str(owner["user_id"]), pipeline, project_id, changeset_id)
    if result.get("error"):
        return result
    return {**result, "executed": False,
            "next_tools": ["nexus_director_pipeline_launch", "nexus_director_pipeline_request_approval"]}


def catalog() -> dict:
    require_owner()
    return {"mode": "deterministic_rules", "external_ai_api": False,
            "pipelines": {key: {"description": spec["description"], "requires_changeset": spec["changeset"],
                                "builds_debug_apk": spec["builds"],
                                "stages": [{"name": n, "agent": STAGES[n][0], "description": STAGES[n][1]} for n in spec["stages"]]}
                          for key, spec in PIPELINES.items()},
            "build_enabled_projects": sorted(PROJECTS), "change_enabled_projects": list(changesets.change_enabled()),
            "automatic_transitions": True, "automatic_retry": False, "automatic_code_fix": False,
            "automatic_publish": False, "modifies_original_source": False,
            "limits": {"active_pipelines_per_owner": MAX_ACTIVE_PER_OWNER, "stage_attempts": MAX_STAGE_ATTEMPTS,
                       "stage_timeout_seconds": STAGE_TIMEOUT_SECONDS}}


# --- storage -----------------------------------------------------------------

def _path(pipeline_id: str):
    return ROOT / (pipeline_id + ".json")


def _load(pipeline_id: str, owner_id: str) -> dict | None:
    if not isinstance(pipeline_id, str) or not ID.fullmatch(pipeline_id):
        return None
    record = store.read(_path(pipeline_id), MAX_RECORD_BYTES)
    if not record or record.get("id") != pipeline_id or record.get("owner") != str(owner_id):
        return None
    return record


def _journal(record: dict, event: dict) -> None:
    try:
        store.append_jsonl(ROOT / "events" / (record["id"] + ".jsonl"), event)
    except (OSError, ValueError):
        pass


def _owned(owner_id: str) -> list[dict]:
    if not ROOT.is_dir():
        return []
    items = []
    for path in sorted(ROOT.glob("pipe-*.json"), key=lambda p: p.name)[:MAX_SCANNED]:
        record = _load(path.stem, owner_id)
        if record:
            items.append(record)
    return sorted(items, key=lambda r: r.get("created_at", ""), reverse=True)


# --- stage executors ----------------------------------------------------------

def _done(**summary) -> dict:
    return {"state": "completed", "summary": summary}


def _fail(error, detail: str = "") -> dict:
    return {"state": "failed", "error": str(error)[:300], "detail": str(detail or "")[-6000:]}


def _stage(record: dict, name: str) -> dict:
    return next((s for s in record["stages"] if s["name"] == name), {})


def _start_inventory(record, stage):
    report = inspect_project(record["project_id"])
    if report.get("error"):
        return _fail(report["error"])
    return _done(counts=report.get("counts"), scene_nodes=report.get("scene_nodes"),
                 findings=len(report.get("findings", [])), files_truncated=report.get("files_truncated"))


def _start_preflight(record, stage):
    outcome = _start_inventory(record, stage)
    if outcome["state"] != "completed":
        return outcome
    if record["project_id"] not in PROJECTS:
        return _fail("project_not_build_enabled")
    try:
        preset = _root(record["project_id"]) / "export_presets.cfg"
        if preset.is_symlink() or not preset.is_file() or preset.stat().st_size > 400_000:
            return _fail("android_preset_unavailable")
        text = preset.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return _fail("project_unavailable")
    if 'platform="Android"' not in text or 'name="Android"' not in text:
        return _fail("android_preset_unavailable")
    return _done(**outcome["summary"], android_preset=True)


def _start_android_audit(record, stage):
    report = android_audit(record["project_id"])
    if report.get("error"):
        return _fail(report["error"])
    return _done(inventory=report.get("inventory"), findings=len(report.get("findings", [])),
                 device_fps_measured=False)


def _start_graphics_audit(record, stage):
    report = graphics_audit(record["project_id"], "balanced")
    if report.get("error"):
        return _fail(report["error"])
    summary = {key: report[key] for key in ("renderer", "dimension", "counts", "features_detected") if key in report}
    return _done(**summary, applied=False)


def _start_audit_report(record, stage):
    return _done(inventory=_stage(record, "inventory").get("summary"),
                 android=_stage(record, "android_audit").get("summary"),
                 graphics=_stage(record, "graphics_audit").get("summary"),
                 detail_tools=["nexus_godot_project_report", "nexus_android_optimization_audit", "nexus_graphics_enhancer_audit"],
                 source_modified=False)


def _changeset(record):
    loaded = changesets.load(record["changeset_id"], record["owner"])
    if loaded is None or loaded["digest"] != record["changeset_digest"]:
        return None
    return loaded


def _start_verify_change(record, stage):
    loaded = _changeset(record)
    if loaded is None:
        return _fail("changeset_not_found")
    gate = changesets.check(loaded)
    if gate.get("error"):
        checks = (gate.get("verification") or {}).get("checks", [])
        return _fail(gate["error"], json.dumps(checks[:20], ensure_ascii=False))
    return _done(verdict=gate["verification"]["verdict"], warnings=gate["verification"]["warnings"],
                 files=len(loaded["files"]), checks=gate["verification"]["checks"][:10])


def _start_validate_change(record, stage):
    loaded = _changeset(record)
    if loaded is None:
        return _fail("changeset_not_found")
    job = changesets.submit_validation(loaded)
    if job.get("error"):
        return _fail(job["error"])
    return {"state": "running", "job_id": job["job_id"]}


def _poll_validate_change(record, stage):
    current = validation_status(stage["job_id"])
    if current.get("error"):
        return {"state": "missing", "error": current["error"]}
    if current["state"] in ("pending", "running"):
        return {"state": "running"}
    result = current.get("result") or {}
    if current["state"] == "completed" and result.get("passed"):
        return _done(validation_job_id=stage["job_id"], workspace_job_id=result.get("workspace_job_id"),
                     godot_exit_code=result.get("godot_exit_code"), original_modified=False)
    return _fail(result.get("error") or "godot_validation_failed", result.get("godot_output", ""))


def _start_build(record, stage):
    job = build_project(record["project_id"])
    if job.get("error"):
        return _fail(job["error"])
    return {"state": "running", "job_id": job["job_id"]}


def _start_build_validated(record, stage):
    job = build_validated(_stage(record, "validate_change").get("job_id") or "")
    if job.get("error"):
        return _fail(job["error"])
    return {"state": "running", "job_id": job["job_id"]}


def _poll_build(record, stage):
    current = build_status(stage["job_id"])
    if current.get("error"):
        return {"state": "missing", "error": current["error"]}
    if current["state"] in ("pending", "running"):
        return {"state": "running"}
    result = current.get("result") or {}
    if current["state"] == "completed" and result.get("passed"):
        return _done(build_job_id=stage["job_id"], bytes=result.get("bytes"), sha256=result.get("sha256"))
    return _fail(result.get("error") or "build_failed", result.get("log", ""))


def _start_change_report(record, stage):
    return _done(verification=_stage(record, "verify_change").get("summary"),
                 validation=_stage(record, "validate_change").get("summary"),
                 applied_to_original=False,
                 note="Изменения проверены только в изолированной копии. Исходный проект не изменён.")


def _start_delivery(record, stage):
    built = _stage(record, "build").get("summary") or _stage(record, "build_validated").get("summary") or {}
    if not built.get("build_job_id") or not built.get("sha256"):
        return _fail("build_failed", "build result missing")
    return _done(build_job_id=built["build_job_id"], sha256=built["sha256"], bytes=built.get("bytes"),
                 next_tool="nexus_godot_apk_download_link", published=False,
                 includes_changeset=bool(record["changeset_id"]))


START = {"inventory": _start_inventory, "android_audit": _start_android_audit, "graphics_audit": _start_graphics_audit,
         "audit_report": _start_audit_report, "preflight": _start_preflight, "build": _start_build,
         "verify_change": _start_verify_change, "validate_change": _start_validate_change,
         "build_validated": _start_build_validated, "change_report": _start_change_report, "delivery": _start_delivery}
POLL = {"validate_change": _poll_validate_change, "build": _poll_build, "build_validated": _poll_build}


# --- state machine ------------------------------------------------------------

def _guard(function, record, stage) -> dict:
    try:
        with _as_owner(record):
            return function(record, stage)
    except Exception as exc:  # A stage can never crash the Director.
        return _fail("stage_exception:" + type(exc).__name__)


def _fail_stage(record, stage, outcome) -> None:
    stage.update({"state": "failed", "error": outcome["error"], "finished_at": store.stamp()})
    entry = errors.record(record["owner"], source="pipeline:" + record["pipeline"], project_id=record["project_id"],
                          stage=stage["name"], error=outcome["error"], detail=outcome.get("detail", ""),
                          reference=record["id"], agent=stage["agent"])
    stage["error_id"] = entry["error_id"]
    stage["diagnostics"] = entry["diagnostics"][:10]
    record["state"] = "failed"
    record["failure"] = {key: entry[key] for key in ("category", "policy", "retryable", "auto_retry", "next_action")}
    _journal(record, {"event": "stage_failed", "stage": stage["name"], "agent": stage["agent"],
                      "error": outcome["error"], "category": entry["category"], "policy": entry["policy"]})


def _advance(record: dict) -> bool:
    """Run every transition that is currently possible. Returns True if changed."""
    changed = False
    expected = _digest(record["pipeline"], record["project_id"], record["changeset_id"], record["changeset_digest"])
    for _ in range(len(record["stages"]) + 1):
        if record["state"] != "running":
            break
        stage = record["stages"][record["current"]]
        if expected != record["plan_digest"]:
            _fail_stage(record, stage, _fail("plan_digest_mismatch"))
            changed = True
            break
        if stage["state"] == "pending":
            stage["attempts"] = stage.get("attempts", 0) + 1
            stage["started_at"] = store.stamp()
            stage["started_unix"] = int(_now())
            outcome = _guard(START[stage["name"]], record, stage)
            if outcome["state"] == "running":
                stage.update({"state": "running", "job_id": outcome["job_id"], "misses": 0})
                _journal(record, {"event": "stage_started", "stage": stage["name"], "agent": stage["agent"],
                                  "job_id": outcome["job_id"], "attempt": stage["attempts"]})
                changed = True
                break
        else:
            outcome = _guard(POLL[stage["name"]], record, stage)
            if outcome["state"] == "missing":
                # A job file moving between queue folders can be invisible for an instant.
                stage["misses"] = stage.get("misses", 0) + 1
                changed = True
                if stage["misses"] < MAX_STATUS_MISSES:
                    break
                outcome = _fail("underlying_job_unavailable", outcome.get("error", ""))
            elif outcome["state"] == "running":
                if _now() - stage.get("started_unix", _now()) > STAGE_TIMEOUT_SECONDS:
                    outcome = _fail("worker_timeout", "stage exceeded %d seconds" % STAGE_TIMEOUT_SECONDS)
                else:
                    if stage.get("misses"):
                        stage["misses"] = 0
                        changed = True
                    break
        changed = True
        if outcome["state"] == "failed":
            _fail_stage(record, stage, outcome)
            break
        stage.update({"state": "completed", "summary": outcome["summary"], "finished_at": store.stamp()})
        _journal(record, {"event": "stage_completed", "stage": stage["name"], "agent": stage["agent"]})
        if record["current"] + 1 >= len(record["stages"]):
            record["state"] = "completed"
            record["finished_at"] = store.stamp()
            _journal(record, {"event": "pipeline_completed"})
        else:
            record["current"] += 1
            _journal(record, {"event": "transition", "to_stage": record["stages"][record["current"]]["name"],
                              "agent": record["stages"][record["current"]]["agent"], "automatic": True})
    return changed


def _advance_locked(pipeline_id: str, owner_id: str) -> dict | None:
    """Advance under an exclusive lock; a concurrent caller just reads the state."""
    with store.lock(ROOT / "locks" / (pipeline_id + ".lock")) as acquired:
        record = _load(pipeline_id, owner_id)
        if record is None or not acquired or record["state"] != "running":
            return record
        if _advance(record):
            record["updated_at"] = store.stamp()
            store.replace(_path(pipeline_id), record)
        return record


def _view(record: dict) -> dict:
    stages = [{key: stage[key] for key in ("name", "agent", "state", "job_id", "attempts", "started_at", "finished_at",
                                           "summary", "error", "error_id", "diagnostics") if stage.get(key) is not None}
              for stage in record["stages"]]
    done = sum(1 for stage in record["stages"] if stage["state"] == "completed")
    current = record["stages"][record["current"]]
    view = {"pipeline_id": record["id"], "pipeline": record["pipeline"], "project_id": record["project_id"],
            "state": record["state"], "progress": "%d/%d" % (done, len(stages)),
            "current_stage": current["name"], "current_agent": current["agent"], "stages": stages,
            "changeset_id": record["changeset_id"] or None, "plan_digest": record["plan_digest"],
            "created_at": record["created_at"], "published": False, "source_modified": False}
    if record["state"] == "failed":
        view["failure"] = {"stage": current["name"], "error": current.get("error"), **record.get("failure", {})}
        view["next_tools"] = ["nexus_director_error_log"] + (["nexus_director_pipeline_retry"] if _can_retry(record) else [])
    elif record["state"] == "completed":
        final = record["stages"][-1].get("summary") or {}
        view["result"] = final
        if final.get("next_tool"):
            view["next_tool"] = final["next_tool"]
    elif record["state"] == "running":
        view["next_tool"] = "nexus_director_pipeline_status"
    return view


def _can_retry(record: dict) -> bool:
    stage = record["stages"][record["current"]]
    return (record["state"] == "failed" and bool(record.get("failure", {}).get("retryable"))
            and stage.get("attempts", 0) < MAX_STAGE_ATTEMPTS)


# --- public operations ---------------------------------------------------------

def launch(pipeline: str, project_id: str, changeset_id: str = "", expected_digest: str = "") -> dict:
    """Authorize and start a pipeline. Requires owner write scope."""
    owner = require_owner_write()
    owner_id = str(owner["user_id"])
    planned = _plan(owner_id, pipeline, project_id, changeset_id)
    if planned.get("error"):
        return planned
    if expected_digest and expected_digest != planned["plan_digest"]:
        return {"error": "plan_digest_mismatch"}
    if sum(1 for record in _owned(owner_id) if record["state"] == "running") >= MAX_ACTIVE_PER_OWNER:
        return {"error": "too_many_active_pipelines", "limit": MAX_ACTIVE_PER_OWNER}
    record = {"id": "pipe-" + uuid.uuid4().hex, "owner": owner_id, "pipeline": pipeline, "project_id": project_id,
              "changeset_id": changeset_id, "changeset_digest": planned["changeset_digest"],
              "plan_digest": planned["plan_digest"], "state": "running", "current": 0,
              "created_at": store.stamp(),
              "stages": [{"name": s["name"], "agent": s["agent"], "state": "pending", "attempts": 0} for s in planned["stages"]]}
    store.write_new(_path(record["id"]), record)
    _journal(record, {"event": "created", "pipeline": pipeline, "project_id": project_id,
                      "plan_digest": record["plan_digest"]})
    return _view(_advance_locked(record["id"], owner_id) or record)


def status(pipeline_id: str) -> dict:
    """Current state. Performs any pending automatic transition first."""
    owner = require_owner()
    record = _advance_locked(pipeline_id, str(owner["user_id"])) if isinstance(pipeline_id, str) and ID.fullmatch(pipeline_id) else None
    if record is None:
        return {"error": "pipeline_not_found"}
    return _view(record)


def journal(pipeline_id: str) -> dict:
    owner = require_owner()
    record = _load(pipeline_id, str(owner["user_id"]))
    if record is None:
        return {"error": "pipeline_not_found"}
    return {"pipeline_id": pipeline_id, "state": record["state"],
            "events": store.read_jsonl(ROOT / "events" / (pipeline_id + ".jsonl"), MAX_JOURNAL)}


def list_pipelines(state: str = "") -> dict:
    owner = require_owner()
    if state not in ("", "running", "completed", "failed", "cancelled"):
        return {"error": "invalid_state"}
    items = [r for r in _owned(str(owner["user_id"])) if not state or r["state"] == state]
    return {"pipelines": [{"pipeline_id": r["id"], "pipeline": r["pipeline"], "project_id": r["project_id"],
                           "state": r["state"], "current_stage": r["stages"][r["current"]]["name"],
                           "current_agent": r["stages"][r["current"]]["agent"], "created_at": r["created_at"]}
                          for r in items[:MAX_LISTED]],
            "truncated": len(items) > MAX_LISTED,
            "note": "Список не выполняет переходы; используйте nexus_director_pipeline_status."}


def cancel(pipeline_id: str) -> dict:
    """Stop all further transitions. A job already handed to the host worker is not interrupted."""
    owner = require_owner_write()
    owner_id = str(owner["user_id"])
    if not isinstance(pipeline_id, str) or not ID.fullmatch(pipeline_id):
        return {"error": "pipeline_not_found"}
    with store.lock(ROOT / "locks" / (pipeline_id + ".lock")) as acquired:
        record = _load(pipeline_id, owner_id)
        if record is None:
            return {"error": "pipeline_not_found"}
        if not acquired:
            return {"error": "pipeline_busy"}
        if record["state"] != "running":
            return {"error": "pipeline_not_running", "state": record["state"]}
        stage = record["stages"][record["current"]]
        in_flight = stage["state"] == "running"
        record.update({"state": "cancelled", "finished_at": store.stamp(), "updated_at": store.stamp()})
        store.replace(_path(pipeline_id), record)
        _journal(record, {"event": "cancelled", "stage": stage["name"], "host_job_in_flight": in_flight})
    return {**_view(record), "host_job_in_flight": in_flight,
            "note": "Дальнейшие этапы не будут запущены." + (" Уже переданное хосту задание завершится само; его результат не используется." if in_flight else "")}


def retry(pipeline_id: str) -> dict:
    """Explicit owner-requested retry of the failed stage, bounded by MAX_STAGE_ATTEMPTS."""
    owner = require_owner_write()
    owner_id = str(owner["user_id"])
    if not isinstance(pipeline_id, str) or not ID.fullmatch(pipeline_id):
        return {"error": "pipeline_not_found"}
    with store.lock(ROOT / "locks" / (pipeline_id + ".lock")) as acquired:
        record = _load(pipeline_id, owner_id)
        if record is None:
            return {"error": "pipeline_not_found"}
        if not acquired:
            return {"error": "pipeline_busy"}
        if record["state"] != "failed":
            return {"error": "pipeline_not_failed", "state": record["state"]}
        if not _can_retry(record):
            return {"error": "retry_not_allowed", "failure": record.get("failure"),
                    "attempts": record["stages"][record["current"]].get("attempts"), "max_attempts": MAX_STAGE_ATTEMPTS}
        if sum(1 for other in _owned(owner_id) if other["state"] == "running") >= MAX_ACTIVE_PER_OWNER:
            return {"error": "too_many_active_pipelines", "limit": MAX_ACTIVE_PER_OWNER}
        stage = record["stages"][record["current"]]
        attempts = stage.get("attempts", 0)
        stage.clear()
        name = PIPELINES[record["pipeline"]]["stages"][record["current"]]
        stage.update({"name": name, "agent": STAGES[name][0], "state": "pending", "attempts": attempts})
        record["state"] = "running"
        record.pop("failure", None)
        _journal(record, {"event": "retry_requested", "stage": stage["name"], "attempt": attempts + 1})
        _advance(record)
        record["updated_at"] = store.stamp()
        store.replace(_path(pipeline_id), record)
    return _view(record)


def agents() -> dict:
    """Agent roles with the stages they execute and the caller's live workload."""
    owner = require_owner()
    running = [r for r in _owned(str(owner["user_id"])) if r["state"] == "running"]
    registry = []
    for agent in AGENTS:
        stages = sorted(name for name, (role, _) in STAGES.items() if role == agent["id"])
        active = [{"pipeline_id": r["id"], "stage": r["stages"][r["current"]]["name"], "project_id": r["project_id"]}
                  for r in running if r["stages"][r["current"]]["agent"] == agent["id"]]
        registry.append({**agent, "status": "active" if stages else "planned", "executor": "deterministic_rules",
                         "model_used": False, "stages": stages, "active_tasks": active})
    return {"agents": registry, "active_pipelines": len(running), "llm_enabled": False,
            "arbitrary_command_execution": False}


def tick(limit: int = 50) -> dict:
    """Worker entry point: advance running pipelines without anyone polling them.

    Not reachable through MCP or HTTP. It can only continue plans that an owner
    already authorized, exactly like a status poll.
    """
    advanced = examined = 0
    if not ROOT.is_dir():
        return {"examined": 0, "advanced": 0}
    for path in sorted(ROOT.glob("pipe-*.json"), key=lambda p: p.name)[:MAX_SCANNED]:
        if examined >= limit:
            break
        record = store.read(path, MAX_RECORD_BYTES)
        if not record or record.get("state") != "running" or record.get("id") != path.stem or not ID.fullmatch(path.stem):
            continue
        examined += 1
        before = (record["current"], record["stages"][record["current"]]["state"])
        after = _advance_locked(path.stem, record["owner"])
        if after and (after["current"], after["stages"][after["current"]]["state"], after["state"]) != (*before, "running"):
            advanced += 1
    return {"examined": examined, "advanced": advanced}
