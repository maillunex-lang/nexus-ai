"""Immutable, SHA-pinned multi-file change sets for registered Godot projects.

A change set is an inert, owner-scoped proposal: full new contents for up to
MAX_FILES existing source files, each pinned to the SHA-256 of the file it
replaces. Creating one writes nothing to any project. It can only ever be
applied to a disposable isolated copy by the separate host worker; originals
are mounted read-only and are never modified.
"""
import hashlib
import json
import os
import re
import uuid
from . import director_store as store
from .director_verification import verify
from .godot_change_preview import preview
from .godot_job_queue import QUEUE, submit as submit_single_file
from .godot_projects import EXCLUDE, _entries, _read, _root
from .mcp_principal import require_owner, require_owner_write

ROOT = QUEUE / "director-changesets"
ID = re.compile(r"cs-[0-9a-f]{32}\Z")
PROJECT = re.compile(r"[a-z][a-z0-9-]{2,39}\Z")
# Mirrors the existing single-file validation queue: widening this list is an
# explicit owner decision, not something a change set can do.
CHANGE_ENABLED = ("basheco",)
MAX_FILES = 8
MAX_TOTAL_BYTES = 100_000
MAX_JOB_BYTES = 140_000     # host worker ignores queue files above 150 kB
MAX_RECORD_BYTES = 900_000
MAX_STORED = 300
MAX_DIFF_TOTAL = 40_000


def digest_of(project_id: str, files: list[dict]) -> str:
    canonical = json.dumps({"project_id": project_id,
                            "files": [{"path": f["path"], "expected_sha256": f["expected_sha256"],
                                       "proposed_sha256": f["proposed_sha256"]} for f in files]},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _exists(root, planned: set):
    def check(relative: str) -> bool:
        if relative in planned:
            return True
        parts = relative.split("/")
        if any(part in ("", ".", "..") for part in parts):
            return False
        cursor = root
        for part in parts:
            cursor = cursor / part
            if cursor.is_symlink():
                return False
        return cursor.is_file()
    return check


def _evaluate(project_id: str, files: list[dict]) -> dict:
    """Re-check every SHA pin against the current source and run the gate."""
    try:
        root = _root(project_id)
    except ValueError as exc:
        return {"error": str(exc)}
    evaluated, sources = [], []
    for item in files:
        result = preview(project_id, item["path"], item["expected_sha256"], item["content"])
        if result.get("error"):
            return {"error": result["error"], "path": item.get("path") if isinstance(item.get("path"), str) else None,
                    **({"current_sha256": result["current_sha256"]} if "current_sha256" in result else {})}
        if not result["changed"]:
            return {"error": "no_changes", "path": item["path"]}
        try:
            old = _read(root.joinpath(*item["path"].split("/")), root) or ""
        except (OSError, ValueError):
            return {"error": "unreadable_or_symlink", "path": item["path"]}
        evaluated.append({"path": item["path"], "expected_sha256": item["expected_sha256"],
                          "proposed_sha256": result["proposed_sha256"], "diff": result["diff"],
                          "diff_truncated": result["diff_truncated"], "findings": result["findings"][:20]})
        sources.append({"path": item["path"], "old": old, "new": item["content"]})
    verification = verify(sources, _exists(root, {f["path"] for f in files}))
    return {"files": evaluated, "verification": verification}


def _valid_shape(files) -> bool:
    return (isinstance(files, list) and 1 <= len(files) <= MAX_FILES and
            all(isinstance(f, dict) and set(f) == {"path", "expected_sha256", "content"} and
                all(isinstance(f[k], str) for k in f) for f in files))


def create(project_id: str, files: list[dict], description: str = "") -> dict:
    """Store an inert change set. An MCP read token may propose; nothing runs."""
    owner = require_owner()
    if not isinstance(project_id, str) or not PROJECT.fullmatch(project_id) or project_id not in _entries():
        return {"error": "unknown_project"}
    if not _valid_shape(files):
        return {"error": "invalid_files", "expected": "1-%d objects with path, expected_sha256, content" % MAX_FILES}
    if len({f["path"] for f in files}) != len(files):
        return {"error": "duplicate_path"}
    if any(part in EXCLUDE for f in files for part in f["path"].split("/")):
        return {"error": "invalid_path"}
    if sum(len(f["content"].encode("utf-8")) for f in files) > MAX_TOTAL_BYTES:
        return {"error": "changeset_too_large", "max_total_bytes": MAX_TOTAL_BYTES}
    if not isinstance(description, str) or len(description) > 1500 or any(ord(c) < 32 and c not in "\n\t" for c in description):
        return {"error": "invalid_description"}
    ROOT.mkdir(parents=True, exist_ok=True)
    if sum(1 for _ in ROOT.glob("cs-*.json")) >= MAX_STORED:
        return {"error": "changeset_quota_exceeded"}
    evaluated = _evaluate(project_id, files)
    if evaluated.get("error"):
        return evaluated
    stored = [{"path": f["path"], "expected_sha256": f["expected_sha256"],
               "proposed_sha256": e["proposed_sha256"], "content": f["content"]}
              for f, e in zip(files, evaluated["files"])]
    record = {"id": "cs-" + uuid.uuid4().hex, "owner": str(owner["user_id"]), "project_id": project_id,
              "description": description, "files": stored, "digest": digest_of(project_id, stored),
              "created_at": store.stamp()}
    store.write_new(ROOT / (record["id"] + ".json"), record)
    return _view(record, evaluated)


def _view(record: dict, evaluated: dict) -> dict:
    budget = MAX_DIFF_TOTAL
    files = []
    for item in evaluated["files"]:
        diff = item["diff"][:max(budget, 0)]
        budget -= len(diff)
        files.append({**item, "diff": diff, "diff_truncated": item["diff_truncated"] or len(diff) < len(item["diff"])})
    verdict = evaluated["verification"]["verdict"]
    enabled = record["project_id"] in CHANGE_ENABLED
    return {"changeset_id": record["id"], "project_id": record["project_id"], "digest": record["digest"],
            "description": record["description"], "created_at": record["created_at"],
            "file_count": len(files), "files": files, "verification": evaluated["verification"],
            "validation_enabled": enabled, "ready_for_validation": enabled and verdict != "block",
            "applied": False, "source_modified": False,
            "next_tool": "nexus_director_pipeline_plan" if enabled and verdict != "block" else None}


def load(changeset_id: str, owner_id: str) -> dict | None:
    """Owner-scoped immutable record whose stored digest still matches its contents."""
    if not isinstance(changeset_id, str) or not ID.fullmatch(changeset_id):
        return None
    record = store.read(ROOT / (changeset_id + ".json"), MAX_RECORD_BYTES)
    if not record or record.get("owner") != str(owner_id) or record.get("id") != changeset_id:
        return None
    try:
        if not _valid_shape([{k: f[k] for k in ("path", "expected_sha256", "content")} for f in record["files"]]):
            return None
        if any(hashlib.sha256(f["content"].encode("utf-8")).hexdigest() != f["proposed_sha256"] for f in record["files"]):
            return None
        if digest_of(record["project_id"], record["files"]) != record["digest"]:
            return None
    except (KeyError, TypeError, AttributeError):
        return None
    return record


def inspect(changeset_id: str) -> dict:
    """Current diff and verification of an owned change set against today's source."""
    owner = require_owner()
    record = load(changeset_id, owner["user_id"])
    if record is None:
        return {"error": "changeset_not_found"}
    evaluated = _evaluate(record["project_id"], record["files"])
    if evaluated.get("error"):
        return {"changeset_id": changeset_id, "project_id": record["project_id"], "digest": record["digest"],
                "stale": True, "ready_for_validation": False, **evaluated}
    return _view(record, evaluated)


def check(record: dict) -> dict:
    """Gate used by pipelines: {} when the change set may be queued, else an error."""
    if record["project_id"] not in CHANGE_ENABLED:
        return {"error": "change_validation_not_enabled", "enabled_projects": list(CHANGE_ENABLED)}
    evaluated = _evaluate(record["project_id"], record["files"])
    if evaluated.get("error"):
        return evaluated
    verification = evaluated["verification"]
    if verification["verdict"] == "block":
        return {"error": "verification_blocked", "verification": verification}
    return {"verification": verification}


def submit_validation(record: dict) -> dict:
    """Queue isolated-copy Godot validation of a verified change set (owner write)."""
    principal = require_owner_write()
    if record.get("owner") != str(principal["user_id"]):
        return {"error": "changeset_not_found"}
    gate = check(record)
    if gate.get("error"):
        return gate
    files = record["files"]
    if len(files) == 1:
        # Identical to the long-standing single-file job understood by every worker version.
        return submit_single_file(record["project_id"], files[0]["path"], files[0]["expected_sha256"], files[0]["content"])
    job = "godot-" + uuid.uuid4().hex
    payload = {"job_id": job, "project_id": record["project_id"],
               "patches": [{"path": f["path"], "expected_sha256": f["expected_sha256"], "content": f["content"]} for f in files],
               "requested_by": str(principal["user_id"])}
    body = json.dumps(payload, ensure_ascii=False)
    if len(body.encode("utf-8")) > MAX_JOB_BYTES:
        return {"error": "changeset_too_large", "max_job_bytes": MAX_JOB_BYTES}
    directory = QUEUE / "pending"
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / (job + ".json")
    fd = os.open(str(final), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
    except BaseException:
        final.unlink(missing_ok=True)
        raise
    return {"job_id": job, "state": "queued", "source_project_modified": False, "files": len(files)}
