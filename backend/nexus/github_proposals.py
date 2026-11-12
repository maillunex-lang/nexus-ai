"""GitHub Agent 5.2: deterministic, read-only patch preview and safety policy.

This module deliberately cannot create branches, write commits or open PRs.
"""
import difflib
import hashlib
import re
from .github_reader import repository_file, repository_head, REPOSITORIES, SHA

MAX_NEW_BYTES = 48_000
MAX_DIFF_BYTES = 80_000
SAFE_PATH = re.compile(r"^[a-zA-Z0-9_.@+/-]{1,240}$")
PROTECTED = {"main", "master", "develop", "release"}
BLOCKED_SEGMENTS = {".git", ".github", ".env", "secrets", "credentials", ".ssh"}
BLOCKED_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".env", ".sqlite", ".db")


def validate_target(repo_id, base_sha, path, branch):
    if repo_id not in REPOSITORIES:
        return "repository_not_allowed"
    if not isinstance(base_sha, str) or not SHA.fullmatch(base_sha):
        return "invalid_base_sha"
    if not isinstance(path, str) or not SAFE_PATH.fullmatch(path) or path.startswith("/"):
        return "invalid_path"
    if any(x in BLOCKED_SEGMENTS or x in ("", ".", "..") for x in path.split("/")) or path.endswith(BLOCKED_SUFFIXES):
        return "protected_path"
    if not isinstance(branch, str) or not re.fullmatch(r"nexus/[a-z0-9][a-z0-9-]{2,48}", branch):
        return "invalid_branch"
    if branch in PROTECTED:
        return "protected_branch"
    return None


def preview_change(repo_id, base_sha, path, proposed_content, branch):
    """Return a bounded diff and its digest, without saving or executing anything."""
    error = validate_target(repo_id, base_sha, path, branch)
    if error:
        return {"error": error}
    if not isinstance(proposed_content, str):
        return {"error": "invalid_content"}
    try:
        encoded = proposed_content.encode("utf-8")
    except UnicodeError:
        return {"error": "invalid_content"}
    if len(encoded) > MAX_NEW_BYTES or "\x00" in proposed_content:
        return {"error": "content_too_large_or_binary"}
    original = repository_file(repo_id, base_sha, path)
    if "error" in original:
        return original
    old = original["content"]
    diff = "".join(difflib.unified_diff(old.splitlines(keepends=True),
                                        proposed_content.splitlines(keepends=True),
                                        fromfile="a/" + path, tofile="b/" + path))
    if len(diff.encode("utf-8")) > MAX_DIFF_BYTES:
        return {"error": "diff_too_large"}
    old_digest = hashlib.sha256(old.encode("utf-8")).hexdigest()
    new_digest = hashlib.sha256(encoded).hexdigest()
    approval_digest = hashlib.sha256(("\n".join((repo_id, base_sha, path, branch, old_digest, new_digest))).encode()).hexdigest()
    return {"repository": repo_id, "base_sha": base_sha, "path": path,
            "proposed_branch": branch, "diff": diff, "original_sha256": old_digest,
            "proposed_sha256": new_digest, "approval_digest": approval_digest,
            "changed": old != proposed_content, "read_only": True,
            "branch_created": False, "pull_request_created": False,
            "tests_executed": False, "note": "Preview only. No repository write or test execution."}


def branch_policy():
    return {"branch_prefix": "nexus/", "protected_branches": sorted(PROTECTED),
            "write_enabled": False, "pull_request_enabled": False,
            "merge_enabled": False, "deploy_enabled": False,
            "required_before_write": ["per-user OAuth identity and mcp:write consent",
                "repository-specific roles", "separate GitHub App installation",
                "exact patch approval and SHA validation", "isolated tests",
                "audit trail and rate limits"],
            "draft_pr_only": True}
