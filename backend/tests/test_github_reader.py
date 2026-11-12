import base64
from unittest.mock import patch
from nexus import github_reader as gh


def test_allowlist():
    assert gh.list_repositories()["writes_enabled"] is False
    assert gh.repository_info("other")["error"] == "repository_not_allowed"
    assert gh.repository_tree("other", "a" * 40)["error"] == "repository_not_allowed"
    assert gh.repository_file("other", "a" * 40, "x.py")["error"] == "repository_not_allowed"


def test_invalid_sha_and_paths_do_not_call_network():
    with patch.object(gh, "_api", side_effect=AssertionError("network call")):
        assert gh.repository_tree("nexus-ai", "main")["error"] == "invalid_commit_sha"
        for path in ("../secret", "/etc/passwd", ".git/config", ".env", "x//y", "x/./y", "x\\y", "x/../y"):
            assert gh.repository_file("nexus-ai", "a" * 40, path)["error"] == "invalid_path"


def test_public_repo_and_head():
    def fake(path):
        if path.endswith("/commits/main"):
            return {"sha": "b" * 40}
        return {"private": False, "full_name": "maillunex-lang/nexus-ai",
                "default_branch": "main", "description": "Test", "updated_at": "2026-11-13"}
    with patch.object(gh, "_api", side_effect=fake):
        assert gh.repository_head("nexus-ai")["head_sha"] == "b" * 40


def test_private_repo_rejected():
    with patch.object(gh, "_api", return_value={"private": True, "full_name": "maillunex-lang/nexus-ai"}):
        assert gh.repository_info("nexus-ai")["error"] == "repository_not_public"


def test_file_bounded_utf8_and_tree():
    content = base64.b64encode(b"print('safe')").decode()
    with patch.object(gh, "_api", return_value={"type": "file", "size": 13, "encoding": "base64", "content": content}):
        assert gh.repository_file("nexus-ai", "a" * 40, "backend/main.py")["content"] == "print('safe')"
    with patch.object(gh, "_api", return_value={"type": "file", "size": gh.MAX_FILE + 1}):
        assert gh.repository_file("nexus-ai", "a" * 40, "backend/main.py")["error"] == "file_too_large"
    with patch.object(gh, "_api", return_value={"tree": [{"path": "backend/main.py", "type": "blob", "size": 13}]}):
        assert gh.repository_tree("nexus-ai", "a" * 40)["entries"][0]["path"] == "backend/main.py"


def test_redirects_disabled():
    assert gh.NoRedirect().redirect_request(None, None, 302, "moved", {}, "https://evil.example") is None
