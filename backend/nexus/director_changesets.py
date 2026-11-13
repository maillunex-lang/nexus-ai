"""Immutable, SHA-pinned multi-file change sets for registered Godot projects.

A change set is an inert, owner-scoped proposal of up to MAX_FILES operations:
  modify  full new contents of an existing file, pinned to its current SHA-256
  create  a new source file at a path that does not exist
  delete  an existing file, pinned to its current SHA-256
(a rename is a delete plus a create). Creating a change set writes nothing to
any project. It can only ever be applied to a disposable isolated copy by the
separate host worker; originals are mounted read-only and are never modified.
"""
import difflib
import hashlib
import json
import os
import re
import uuid
from . import director_settings as settings
from . import director_store as store
from .director_verification import verify
from .godot_change_preview import EDITABLE, MAX_DIFF, preview
from .godot_job_queue import QUEUE, submit as submit_single_file
from .godot_projects import EXCLUDE, MAX_BYTES, _entries, _files, _read, _root
from .mcp_principal import require_owner, require_owner_write

ROOT = QUEUE / "director-changesets"
ID = re.compile(r"cs-[0-9a-f]{32}\Z")
PROJECT = re.compile(r"[a-z][a-z0-9-]{2,39}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
CHANGE_ENABLED = settings.BASELINE   # baseline only; see change_enabled()
ACTIONS = ("modify", "create", "delete")
REQUIRED = {"modify": {"path", "expected_sha256", "content"}, "create": {"path", "content"},
            "delete": {"path", "expected_sha256"}}
MAX_FILES = 8
MAX_TOTAL_BYTES = 100_000
MAX_JOB_BYTES = 140_000     # host worker ignores queue files above 150 kB
MAX_RECORD_BYTES = 900_000
MAX_STORED = 300
MAX_DIFF_TOTAL = 40_000


def change_enabled() -> tuple:
    """Projects whose change sets may be validated: baseline plus the owner's choices."""
    return settings.change_enabled()


def digest_of(project_id: str, files: list[dict]) -> str:
    items = []
    for f in files:
        item = {"path": f["path"], "expected_sha256": f["expected_sha256"], "proposed_sha256": f["proposed_sha256"]}
        if f.get("action", "modify") != "modify":
            item["action"] = f["action"]
        items.append(item)
    canonical = json.dumps({"project_id": project_id, "files": items}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parts(path):
    if not isinstance(path, str) or not path or len(path) > 240 or path.startswith("/") or "\\" in path:
        return None
    parts = path.split("/")
    if any(part in ("", ".", "..") or part in EXCLUDE for part in parts):
        return None
    return parts


def _present(root, relative: str) -> bool:
    parts = _parts(relative)
    if parts is None:
        return False
    cursor = root
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return False
    return cursor.is_file()


def _normalize(files):
    """Validate the caller's operations and return them in stored form, or None."""
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        return None
    normalized = []
    for item in files:
        if not isinstance(item, dict) or not all(isinstance(value, str) for value in item.values()):
            return None
        action = item.get("action", "modify")
        if action not in ACTIONS or set(item) - {"action"} != REQUIRED[action]:
            return None
        normalized.append({"action": action, "path": item["path"],
                           "expected_sha256": item.get("expected_sha256", ""), "content": item.get("content", "")})
    return normalized


def _diff(old: str, new: str, path: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                        fromfile="current/" + path, tofile="proposed/" + path))


def _evaluate_create(root, item) -> dict:
    parts = _parts(item["path"])
    if parts is None:
        return {"error": "invalid_path"}
    content = item["content"]
    if len(content.encode("utf-8")) > MAX_BYTES or "\x00" in content:
        return {"error": "invalid_content"}
    target = root.joinpath(*parts)
    if target.suffix not in EDITABLE:
        return {"error": "unsupported_file_type"}
    cursor = root
    for index, part in enumerate(parts):
        cursor = cursor / part
        if cursor.is_symlink():
            return {"error": "unreadable_or_symlink"}
        if index < len(parts) - 1 and cursor.exists() and not cursor.is_dir():
            return {"error": "invalid_path"}
    if os.path.lexists(target):
        return {"error": "already_exists"}
    delta = _diff("", content, item["path"])
    return {"old": "", "proposed_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "diff": delta[:MAX_DIFF], "diff_truncated": len(delta) > MAX_DIFF, "findings": []}


def _evaluate_delete(root, item) -> dict:
    parts = _parts(item["path"])
    if parts is None:
        return {"error": "invalid_path"}
    if not SHA.fullmatch(item["expected_sha256"]):
        return {"error": "invalid_sha256"}
    target = root.joinpath(*parts)
    if target.suffix not in EDITABLE:
        return {"error": "unsupported_file_type"}
    if not target.is_file():
        return {"error": "not_found"}
    try:
        old = _read(target, root)
    except (OSError, ValueError):
        return {"error": "unreadable_or_symlink"}
    if old is None:
        return {"error": "file_too_large"}
    current = hashlib.sha256(old.encode("utf-8")).hexdigest()
    if current != item["expected_sha256"]:
        return {"error": "source_changed", "current_sha256": current}
    delta = _diff(old, "", item["path"])
    return {"old": old, "proposed_sha256": "", "diff": delta[:MAX_DIFF],
            "diff_truncated": len(delta) > MAX_DIFF, "findings": []}


def _evaluate_modify(project_id, root, item) -> dict:
    result = preview(project_id, item["path"], item["expected_sha256"], item["content"])
    if result.get("error"):
        return result
    if not result["changed"]:
        return {"error": "no_changes"}
    try:
        old = _read(root.joinpath(*item["path"].split("/")), root) or ""
    except (OSError, ValueError):
        return {"error": "unreadable_or_symlink"}
    return {"old": old, "proposed_sha256": result["proposed_sha256"], "diff": result["diff"],
            "diff_truncated": result["diff_truncated"], "findings": result["findings"][:20]}


def _dangling_references(root, files) -> list[dict]:
    """Warn when a deleted file is still referenced by what remains after the change."""
    deleted = [f["path"] for f in files if f["action"] == "delete"]
    if not deleted:
        return []
    replaced = {f["path"]: f["content"] for f in files if f["action"] != "delete"}
    texts = dict(replaced)
    for file in _files(root)[0]:
        relative = file.relative_to(root).as_posix()
        if relative in replaced or relative in deleted:
            continue
        try:
            texts[relative] = _read(file, root) or ""
        except (OSError, ValueError):
            continue
    checks = []
    for path in deleted:
        users = sorted(name for name, text in texts.items() if "res://" + path in text)[:5]
        if users:
            checks.append({"path": path, "code": "deleted_file_still_referenced", "severity": "warn",
                           "message": "Удаляемый файл всё ещё используется: " + ", ".join(users)})
    return checks


def _evaluate(project_id: str, files: list[dict]) -> dict:
    """Re-check every operation against the current source and run the gate."""
    try:
        root = _root(project_id)
    except ValueError as exc:
        return {"error": str(exc)}
    evaluated, sources = [], []
    for item in files:
        action = item.get("action", "modify")
        result = (_evaluate_create(root, item) if action == "create" else
                  _evaluate_delete(root, item) if action == "delete" else _evaluate_modify(project_id, root, item))
        if result.get("error"):
            return {"error": result["error"], "path": item["path"] if isinstance(item.get("path"), str) else None,
                    **({"current_sha256": result["current_sha256"]} if "current_sha256" in result else {})}
        evaluated.append({"action": action, "path": item["path"], "expected_sha256": item["expected_sha256"],
                          "proposed_sha256": result["proposed_sha256"], "diff": result["diff"],
                          "diff_truncated": result["diff_truncated"], "findings": result["findings"]})
        if action != "delete":
            sources.append({"path": item["path"], "old": result["old"], "new": item["content"]})
    planned = {f["path"] for f in files if f.get("action", "modify") != "delete"}
    removed = {f["path"] for f in files if f.get("action", "modify") == "delete"}
    exists = lambda relative: relative in planned or (relative not in removed and _present(root, relative))
    normalized = [{**f, "action": f.get("action", "modify")} for f in files]
    return {"files": evaluated, "verification": verify(sources, exists, _dangling_references(root, normalized))}


def create(project_id: str, files: list[dict], description: str = "") -> dict:
    """Store an inert change set. An MCP read token may propose; nothing runs."""
    owner = require_owner()
    if not isinstance(project_id, str) or not PROJECT.fullmatch(project_id) or project_id not in _entries():
        return {"error": "unknown_project"}
    normalized = _normalize(files)
    if normalized is None:
        return {"error": "invalid_files",
                "expected": "1-%d objects: modify {path, expected_sha256, content}; "
                            "{action:'create', path, content}; {action:'delete', path, expected_sha256}" % MAX_FILES}
    if len({f["path"] for f in normalized}) != len(normalized):
        return {"error": "duplicate_path"}
    if any(_parts(f["path"]) is None for f in normalized):
        return {"error": "invalid_path"}
    if sum(len(f["content"].encode("utf-8")) for f in normalized) > MAX_TOTAL_BYTES:
        return {"error": "changeset_too_large", "max_total_bytes": MAX_TOTAL_BYTES}
    if not isinstance(description, str) or len(description) > 1500 or any(ord(c) < 32 and c not in "\n\t" for c in description):
        return {"error": "invalid_description"}
    ROOT.mkdir(parents=True, exist_ok=True)
    if sum(1 for _ in ROOT.glob("cs-*.json")) >= MAX_STORED:
        return {"error": "changeset_quota_exceeded"}
    evaluated = _evaluate(project_id, normalized)
    if evaluated.get("error"):
        return evaluated
    stored = [{**f, "proposed_sha256": e["proposed_sha256"]} for f, e in zip(normalized, evaluated["files"])]
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
    enabled = record["project_id"] in change_enabled()
    return {"changeset_id": record["id"], "project_id": record["project_id"], "digest": record["digest"],
            "description": record["description"], "created_at": record["created_at"],
            "file_count": len(files), "files": files, "verification": evaluated["verification"],
            "operations": {action: sum(1 for f in files if f["action"] == action) for action in ACTIONS},
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
        files = record["files"]
        if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
            return None
        for f in files:
            f.setdefault("action", "modify")   # records written before create/delete existed
            if f["action"] not in ACTIONS or not all(isinstance(f[k], str) for k in ("path", "expected_sha256", "content", "proposed_sha256")):
                return None
            expected = "" if f["action"] == "delete" else hashlib.sha256(f["content"].encode("utf-8")).hexdigest()
            if f["proposed_sha256"] != expected:
                return None
        if digest_of(record["project_id"], files) != record["digest"]:
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
    if record["project_id"] not in change_enabled():
        return {"error": "change_validation_not_enabled", "enabled_projects": list(change_enabled())}
    evaluated = _evaluate(record["project_id"], record["files"])
    if evaluated.get("error"):
        return evaluated
    verification = evaluated["verification"]
    if verification["verdict"] == "block":
        return {"error": "verification_blocked", "verification": verification}
    return {"verification": verification}


def _patch(f: dict) -> dict:
    if f["action"] == "create":
        return {"action": "create", "path": f["path"], "content": f["content"]}
    if f["action"] == "delete":
        return {"action": "delete", "path": f["path"], "expected_sha256": f["expected_sha256"]}
    return {"path": f["path"], "expected_sha256": f["expected_sha256"], "content": f["content"]}


def submit_validation(record: dict) -> dict:
    """Queue isolated-copy Godot validation of a verified change set (owner write)."""
    principal = require_owner_write()
    if record.get("owner") != str(principal["user_id"]):
        return {"error": "changeset_not_found"}
    gate = check(record)
    if gate.get("error"):
        return gate
    files = record["files"]
    if len(files) == 1 and files[0]["action"] == "modify" and record["project_id"] in settings.BASELINE:
        # Identical to the long-standing single-file job understood by every worker version.
        return submit_single_file(record["project_id"], files[0]["path"], files[0]["expected_sha256"], files[0]["content"])
    job = "godot-" + uuid.uuid4().hex
    payload = {"job_id": job, "project_id": record["project_id"], "patches": [_patch(f) for f in files],
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
