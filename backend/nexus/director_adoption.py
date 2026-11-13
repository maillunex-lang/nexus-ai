"""Adopting a validated change set: patch export and opt-in GitHub draft pull request.

Two ways out of the sandbox, neither of which can touch a live game directory:

1. patch()   A git-compatible patch of the change set for the owner to apply
             by hand (`git apply`). Read only, always available.
2. execute() A new `nexus/adopt-*` branch with ONE commit on top of the
             configured base branch of the game's GitHub repository, plus a
             draft pull request. Disabled until the server operator provides a
             repository mapping and a token file. Reachable only through an
             owner-approved request in the dashboard, never directly via MCP.

Hard rules for (2): only change sets that completed an isolated Godot
validation pipeline; every modified or deleted file in the repository must be
byte-identical (SHA-256) to the source the change was validated against; the
branch is created, never updated; base and protected branches are never
written; nothing is ever merged or deployed.
"""
import base64
import difflib
import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener
from . import director_changesets as changesets
from . import director_pipelines as pipelines
from . import director_store as store
from .github_proposals import BLOCKED_SEGMENTS, BLOCKED_SUFFIXES, PROTECTED
from .github_reader import NoRedirect
from .godot_job_queue import QUEUE
from .godot_projects import _read, _root
from .mcp_principal import require_owner, require_owner_write

ROOT = QUEUE / "director-adoptions"
REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,38}/[A-Za-z0-9_.-]{1,100}\Z")
BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}\Z")
PREFIX = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+){0,7}\Z")
DEFAULT_TOKEN_FILE = "/run/secrets/github_adoption_token"
MAX_RESPONSE = 600_000
MAX_PATCH_BYTES = 400_000
VALIDATING = ("change_validate", "change_build_apk")


# --- configuration -------------------------------------------------------------

def targets() -> dict:
    """NEXUS_ADOPTION_REPOSITORIES: {"project": {"repository": "owner/name",
    "base_branch": "main", "path_prefix": "client"}}. Invalid entries are ignored."""
    try:
        raw = json.loads(os.environ.get("NEXUS_ADOPTION_REPOSITORIES", "") or "{}")
    except ValueError:
        return {}
    result = {}
    for project, entry in (raw.items() if isinstance(raw, dict) else ()):
        if not isinstance(project, str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,39}", project) or not isinstance(entry, dict):
            continue
        repository, base, prefix = entry.get("repository"), entry.get("base_branch", "main"), entry.get("path_prefix", "")
        if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository) or ".." in repository:
            continue
        if not isinstance(base, str) or not BRANCH.fullmatch(base) or ".." in base or base.startswith("nexus/"):
            continue
        if not isinstance(prefix, str) or (prefix and (not PREFIX.fullmatch(prefix) or any(p in (".", "..") for p in prefix.split("/")))):
            continue
        result[project] = {"repository": repository, "base_branch": base, "path_prefix": prefix}
    return result


def _token() -> str:
    path = Path(os.environ.get("NEXUS_GITHUB_ADOPTION_TOKEN_FILE", DEFAULT_TOKEN_FILE))
    try:
        if not path.is_file() or path.stat().st_size > 4096:
            return ""
        token = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return token if re.fullmatch(r"[A-Za-z0-9_\-.]{20,400}", token) else ""


def describe() -> dict:
    """Where adoption is possible. Never reveals the token."""
    require_owner()
    configured = targets()
    return {"patch_export": True, "github_enabled": bool(configured) and bool(_token()),
            "credentials_present": bool(_token()),
            "repositories": [{"project_id": key, **value} for key, value in sorted(configured.items())],
            "requires_owner_dashboard_approval": True, "draft_pull_request_only": True,
            "merge_enabled": False, "deploy_enabled": False, "writes_live_game_directory": False}


# --- patch export ---------------------------------------------------------------

def _hunks(old: str, new: str, path: str, action: str) -> str:
    lines = list(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                      fromfile="/dev/null" if action == "create" else "a/" + path,
                                      tofile="/dev/null" if action == "delete" else "b/" + path))
    return "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in lines)


def _sources(record: dict) -> list[dict] | None:
    """Current original text of every touched file; None when the pins no longer hold."""
    if changesets._evaluate(record["project_id"], record["files"]).get("error"):
        return None
    root = _root(record["project_id"])
    items = []
    for f in record["files"]:
        old = "" if f["action"] == "create" else (_read(root.joinpath(*f["path"].split("/")), root) or "")
        items.append({**f, "old": old})
    return items


def patch(changeset_id: str) -> dict:
    """Git-compatible patch of an owned, still-current change set. Applies nothing."""
    owner = require_owner()
    record = changesets.load(changeset_id, str(owner["user_id"]))
    if record is None:
        return {"error": "changeset_not_found"}
    try:
        sources = _sources(record)
    except (ValueError, OSError):
        sources = None
    if sources is None:
        return {"error": "changeset_stale", "note": "Исходные файлы изменились; создайте новый набор изменений."}
    parts = []
    for f in sources:
        header = "diff --git a/%s b/%s\n" % (f["path"], f["path"])
        if f["action"] == "create":
            header += "new file mode 100644\n"
        elif f["action"] == "delete":
            header += "deleted file mode 100644\n"
        parts.append(header + _hunks(f["old"], f["content"], f["path"], f["action"]))
    text = "".join(parts)
    if len(text.encode("utf-8")) > MAX_PATCH_BYTES:
        return {"error": "patch_too_large"}
    validated = pipelines.validated_run(str(owner["user_id"]), record["id"], record["digest"])
    return {"changeset_id": record["id"], "project_id": record["project_id"], "digest": record["digest"],
            "patch": text, "patch_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "filename": "nexus-" + record["id"][3:11] + ".patch",
            "validated_in_isolated_copy": bool(validated), "validation_pipeline_id": validated,
            "apply_with": "git checkout -b nexus/adopt-%s && git apply --check FILE && git apply FILE" % record["id"][3:11],
            "applied": False, "source_modified": False,
            "note": "Пути указаны относительно корня проекта Godot. Патч никуда не применён."}


# --- GitHub draft pull request ---------------------------------------------------

def plan(owner_id: str, changeset_id: str) -> dict:
    """Everything an adoption would do, or the reason it cannot happen. No network, no writes."""
    record = changesets.load(changeset_id, owner_id)
    if record is None:
        return {"error": "changeset_not_found"}
    target = targets().get(record["project_id"])
    if target is None:
        return {"error": "adoption_not_configured", "project_id": record["project_id"],
                "alternative_tool": "nexus_director_changeset_patch"}
    if not _token():
        return {"error": "adoption_credentials_missing", "alternative_tool": "nexus_director_changeset_patch"}
    validated = pipelines.validated_run(owner_id, record["id"], record["digest"])
    if not validated:
        return {"error": "validated_pipeline_required",
                "note": "Сначала завершите конвейер change_validate или change_build_apk для этого набора."}
    prefix = target["path_prefix"]
    paths = [(prefix + "/" if prefix else "") + f["path"] for f in record["files"]]
    for path in paths:
        if any(part in BLOCKED_SEGMENTS for part in path.split("/")) or path.endswith(BLOCKED_SUFFIXES):
            return {"error": "protected_path", "path": path}
    digest = hashlib.sha256(json.dumps({"changeset": record["digest"], **target}, sort_keys=True).encode()).hexdigest()
    return {"changeset_id": record["id"], "project_id": record["project_id"], "changeset_digest": record["digest"],
            **target, "repository_paths": paths, "validation_pipeline_id": validated, "adoption_digest": digest,
            "branch_prefix": "nexus/adopt-", "draft_pull_request": True, "merge": False, "deploy": False,
            "writes_live_game_directory": False}


def _github(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    request = Request("https://api.github.com" + path, method=method,
                      data=json.dumps(body).encode("utf-8") if body is not None else None,
                      headers={"Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
                               "User-Agent": "NEXUS-AI-adoption/0.6", "X-GitHub-Api-Version": "2022-11-28",
                               "Content-Type": "application/json"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=12) as response:
            data = response.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                return 0, {}
            parsed = json.loads(data) if data else {}
            return response.status, parsed if isinstance(parsed, dict) else {}
    except HTTPError as exc:
        return exc.code, {}
    except (URLError, TimeoutError, ValueError, OSError):
        return 0, {}


def _audit(owner_id: str, event: dict) -> None:
    try:
        store.append_jsonl(ROOT / "audit.jsonl", {"actor": owner_id, **event})
    except (OSError, ValueError):
        pass


def execute(changeset_id: str, expected_digest: str, description: str = "") -> dict:
    """Create the branch, single commit and draft PR. Called only from an approved owner request."""
    owner = require_owner_write()
    owner_id = str(owner["user_id"])
    planned = plan(owner_id, changeset_id)
    if planned.get("error"):
        return planned
    if planned["adoption_digest"] != expected_digest:
        return {"error": "adoption_digest_mismatch"}
    record = changesets.load(changeset_id, owner_id)
    if changesets._evaluate(record["project_id"], record["files"]).get("error"):
        return {"error": "changeset_stale"}
    token, repo, base = _token(), "/repos/" + planned["repository"], planned["base_branch"]
    status, ref = _github("GET", repo + "/git/ref/heads/" + quote(base, safe="/"), token)
    base_sha = (ref.get("object") or {}).get("sha") if status == 200 else None
    if not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", base_sha):
        return {"error": "base_branch_unavailable", "status": status}
    status, commit = _github("GET", repo + "/git/commits/" + base_sha, token)
    tree_sha = (commit.get("tree") or {}).get("sha") if status == 200 else None
    if not isinstance(tree_sha, str):
        return {"error": "base_commit_unavailable", "status": status}
    entries = []
    for f, path in zip(record["files"], planned["repository_paths"]):
        status, blob = _github("GET", repo + "/contents/" + quote(path, safe="/") + "?ref=" + base_sha, token)
        if f["action"] == "create":
            if status != 404:
                return {"error": "already_exists_in_repository" if status == 200 else "repository_unavailable", "path": path}
        else:
            if status != 200 or blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
                return {"error": "repository_file_unavailable", "path": path, "status": status}
            try:
                current = hashlib.sha256(base64.b64decode(blob["content"])).hexdigest()
            except ValueError:
                return {"error": "repository_file_unavailable", "path": path}
            if current != f["expected_sha256"]:
                # The repository is not the source this change was validated against.
                return {"error": "repository_differs_from_validated_source", "path": path}
        entry = {"path": path, "mode": "100644", "type": "blob"}
        entry.update({"sha": None} if f["action"] == "delete" else {"content": f["content"]})
        entries.append(entry)
    status, tree = _github("POST", repo + "/git/trees", token, {"base_tree": tree_sha, "tree": entries})
    if status != 201 or not isinstance(tree.get("sha"), str):
        return {"error": "tree_creation_failed", "status": status}
    title = "NEXUS: adopt validated change set " + record["id"][3:11]
    message = (title + "\n\n" + (description or record.get("description") or "").strip()[:1500] +
               "\n\nChange set: %s\nDigest: %s\nValidated by pipeline: %s\n" %
               (record["id"], record["digest"], planned["validation_pipeline_id"]))
    status, created = _github("POST", repo + "/git/commits", token,
                              {"message": message, "tree": tree["sha"], "parents": [base_sha]})
    if status != 201 or not isinstance(created.get("sha"), str):
        return {"error": "commit_creation_failed", "status": status}
    branch = "nexus/adopt-%s-%s" % (record["id"][3:11], secrets.token_hex(3))
    if branch in PROTECTED or branch == base:
        return {"error": "protected_branch"}
    status, _ = _github("POST", repo + "/git/refs", token, {"ref": "refs/heads/" + branch, "sha": created["sha"]})
    if status != 201:
        return {"error": "branch_creation_failed", "status": status}
    result = {"repository": planned["repository"], "branch": branch, "base_branch": base, "base_sha": base_sha,
              "commit_sha": created["sha"], "files": len(entries), "merged": False, "deployed": False,
              "live_game_directory_modified": False}
    status, pull = _github("POST", repo + "/pulls", token,
                           {"title": title, "head": branch, "base": base, "draft": True, "body": message})
    if status == 201 and isinstance(pull.get("html_url"), str):
        result.update({"pull_request_url": pull["html_url"], "pull_request_number": pull.get("number"), "draft": True})
    else:
        result.update({"pull_request_url": None, "pull_request_error": "draft_pull_request_failed", "status": status,
                       "note": "Ветка создана. Откройте pull request вручную."})
    _audit(owner_id, {"event": "adopted", "changeset_id": record["id"], **{k: result[k] for k in ("repository", "branch", "commit_sha")}})
    return result
