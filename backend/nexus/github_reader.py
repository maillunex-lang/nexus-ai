"""Public GitHub repository reader for explicit allowlisted repositories only.

No credentials, git commands, checkout, mutations or arbitrary URLs.
"""
import base64
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

REPOSITORIES = {"nexus-ai": "maillunex-lang/nexus-ai"}
MAX_RESPONSE = 450_000
MAX_FILE = 96_000
MAX_ENTRIES = 250
MAX_PATH = 240
SHA = re.compile(r"^[0-9a-f]{40}$")
PATH = re.compile(r"^[a-zA-Z0-9_.@+/-]+$")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _api(path):
    url = "https://api.github.com" + path
    request = Request(url, headers={"Accept": "application/vnd.github+json",
                                     "User-Agent": "NEXUS-AI-readonly/0.5",
                                     "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            if response.status != 200:
                return {"error": "upstream_failure"}
            data = response.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                return {"error": "response_too_large"}
            return json.loads(data)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return {"error": "upstream_unavailable"}


def _repo(repo_id):
    return REPOSITORIES.get(repo_id) if isinstance(repo_id, str) else None


def list_repositories():
    return {"repositories": [{"id": key, "full_name": value, "read_only": True,
                               "public_only": True} for key, value in REPOSITORIES.items()],
            "writes_enabled": False}


def repository_info(repo_id):
    repo = _repo(repo_id)
    if not repo:
        return {"error": "repository_not_allowed"}
    data = _api("/repos/" + repo)
    if not isinstance(data, dict) or "error" in data:
        return data
    if data.get("private") is not False or data.get("full_name", "").lower() != repo.lower():
        return {"error": "repository_not_public"}
    return {"id": repo_id, "full_name": repo, "default_branch": data.get("default_branch"),
            "description": (data.get("description") or "")[:500],
            "updated_at": data.get("updated_at"), "read_only": True}


def repository_tree(repo_id, commit_sha):
    repo = _repo(repo_id)
    if not repo:
        return {"error": "repository_not_allowed"}
    if not isinstance(commit_sha, str) or not SHA.fullmatch(commit_sha):
        return {"error": "invalid_commit_sha"}
    data = _api("/repos/" + repo + "/git/trees/" + commit_sha + "?recursive=1")
    if not isinstance(data, dict) or "error" in data:
        return data
    entries = data.get("tree")
    if not isinstance(entries, list):
        return {"error": "invalid_upstream_response"}
    files = [{"path": item["path"], "type": item["type"], "size": item.get("size")}
             for item in entries if isinstance(item, dict)
             and item.get("type") in ("blob", "tree")
             and isinstance(item.get("path"), str)][:MAX_ENTRIES]
    return {"repository": repo_id, "commit_sha": commit_sha, "entries": files,
            "truncated": bool(data.get("truncated")) or len(entries) > MAX_ENTRIES,
            "read_only": True}


def repository_file(repo_id, commit_sha, path):
    repo = _repo(repo_id)
    if not repo:
        return {"error": "repository_not_allowed"}
    if not isinstance(commit_sha, str) or not SHA.fullmatch(commit_sha):
        return {"error": "invalid_commit_sha"}
    if (not isinstance(path, str) or len(path) > MAX_PATH or not PATH.fullmatch(path)
            or path.startswith("/") or any(part in ("", ".", "..") for part in path.split("/"))
            or any(part in (".git", ".env", ".github") for part in path.split("/"))):
        return {"error": "invalid_path"}
    data = _api("/repos/" + repo + "/contents/" + quote(path, safe="/") + "?ref=" + commit_sha)
    if not isinstance(data, dict) or "error" in data:
        return data
    if data.get("type") != "file" or not isinstance(data.get("size"), int):
        return {"error": "not_a_file"}
    if data["size"] > MAX_FILE:
        return {"error": "file_too_large"}
    if data.get("encoding") != "base64" or not isinstance(data.get("content"), str):
        return {"error": "unsupported_encoding"}
    try:
        raw = base64.b64decode(data["content"], validate=False)
        if len(raw) > MAX_FILE:
            return {"error": "file_too_large"}
        content = raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return {"error": "not_utf8_text"}
    return {"repository": repo_id, "commit_sha": commit_sha, "path": path,
            "content": content, "size": len(raw), "read_only": True}
