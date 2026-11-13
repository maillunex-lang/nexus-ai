"""Bounded retention for Director state files in the queue volume.

Removes only finished Director records older than the retention period:
terminal pipelines (with their journals), change sets no longer referenced by a
kept pipeline or a pending approval request, rotated error journals and stale
lock files. Never touches game projects, workspaces, builds, the host job
queues or approval requests.
"""
import os
import time
from datetime import datetime
from . import director_changesets, director_errors, director_pipelines
from . import director_store as store
from .godot_job_queue import QUEUE

DEFAULT_DAYS = 30
MAX_SCANNED = 2000


def retention_days() -> int:
    """NEXUS_DIRECTOR_RETENTION_DAYS: 0 disables, default 30, otherwise 1-3650."""
    raw = os.environ.get("NEXUS_DIRECTOR_RETENTION_DAYS", "")
    if not raw:
        return DEFAULT_DAYS
    try:
        days = int(raw)
    except ValueError:
        return DEFAULT_DAYS
    return days if 0 <= days <= 3650 else DEFAULT_DAYS


def _age(value, fallback: float) -> float:
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return fallback


def _remove(path) -> bool:
    try:
        if path.is_symlink() or not path.is_file():
            return False
        path.unlink()
        return True
    except OSError:
        return False


def purge(days: int | None = None, now: float | None = None) -> dict:
    days = retention_days() if days is None else days
    result = {"retention_days": days, "pipelines": 0, "changesets": 0, "error_archives": 0, "locks": 0}
    if days <= 0:
        return {**result, "disabled": True}
    now = time.time() if now is None else now
    cutoff = now - days * 86400
    referenced = set()
    pipelines = director_pipelines.ROOT
    if pipelines.is_dir():
        for path in sorted(pipelines.glob("pipe-*.json"))[:MAX_SCANNED]:
            record = store.read(path, director_pipelines.MAX_RECORD_BYTES)
            if not record:
                continue
            finished = _age(record.get("finished_at") or record.get("updated_at") or record.get("created_at"), now)
            if record.get("state") in ("completed", "failed", "cancelled") and finished < cutoff:
                if _remove(path):
                    result["pipelines"] += 1
                    _remove(pipelines / "events" / (path.stem + ".jsonl"))
                continue
            if record.get("changeset_id"):
                referenced.add(record["changeset_id"])
        locks = pipelines / "locks"
        if locks.is_dir():
            for path in sorted(locks.glob("*.lock"))[:MAX_SCANNED]:
                try:
                    stale = now - path.lstat().st_mtime > 86400
                except OSError:
                    continue
                if stale and _remove(path):
                    result["locks"] += 1
    requests = QUEUE / "director-requests"
    if requests.is_dir():
        for path in sorted(requests.glob("req-*.json"))[:MAX_SCANNED]:
            record = store.read(path, 12000)
            if record and record.get("status") == "pending" and record.get("changeset_id"):
                referenced.add(record["changeset_id"])
    changesets = director_changesets.ROOT
    if changesets.is_dir():
        for path in sorted(changesets.glob("cs-*.json"))[:MAX_SCANNED]:
            if path.stem in referenced:
                continue
            record = store.read(path, director_changesets.MAX_RECORD_BYTES)
            try:
                created = _age((record or {}).get("created_at"), path.lstat().st_mtime)
            except OSError:
                continue
            if created < cutoff and _remove(path):
                result["changesets"] += 1
    journals = director_errors.ROOT
    if journals.is_dir():
        for path in sorted(journals.glob("*.jsonl.1"))[:MAX_SCANNED]:
            try:
                old = path.lstat().st_mtime < cutoff
            except OSError:
                continue
            if old and _remove(path):
                result["error_archives"] += 1
    return result
