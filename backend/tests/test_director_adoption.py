"""Stage 8: patch export and approval-gated GitHub draft pull request."""
import base64
import hashlib
import json
import subprocess
from contextlib import contextmanager
from unittest.mock import patch
from fastapi.testclient import TestClient
from nexus import dashboard_director, director_requests
from nexus import director_adoption as a
from nexus import director_changesets as c
from nexus import director_pipelines as p
from nexus.main import app
from nexus.mcp_principal import principal_var
from test_director_pipelines import env, host_finish, stage, scope, OLD

TOKEN = "ghp_" + "x" * 36
CONFIG = json.dumps({"basheco": {"repository": "acme/basheco", "base_branch": "main", "path_prefix": "client"}})
BASE = "b" * 40
OWNER = {"id": "owner-1", "roles": ["owner"]}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def operations():
    return [{"path": "scripts/a.gd", "expected_sha256": sha(OLD), "content": "extends Node\nvar speed = 3"},
            {"action": "create", "path": "ui/hud.gd", "content": "extends Control\n"},
            {"action": "delete", "path": "scripts/b.gd", "expected_sha256": sha(OLD)}]


def validated_changeset(queue):
    cs = c.create("basheco", operations(), "Speed and HUD")
    view = p.launch("change_validate", "basheco", cs["changeset_id"])
    host_finish(queue, "pending", "completed", stage(view, "validate_change")["job_id"],
                {"passed": True, "workspace_job_id": "godot-" + "c" * 32})
    assert p.status(view["pipeline_id"])["state"] == "completed"
    return cs, view["pipeline_id"]


@contextmanager
def configured(tmp_path, monkeypatch, queue):
    token_file = tmp_path / "token"
    token_file.write_text(TOKEN + "\n")
    monkeypatch.setenv("NEXUS_ADOPTION_REPOSITORIES", CONFIG)
    monkeypatch.setenv("NEXUS_GITHUB_ADOPTION_TOKEN_FILE", str(token_file))
    with patch.object(a, "ROOT", queue / "director-adoptions"), patch.object(director_requests, "ROOT", queue / "director-requests"):
        yield


class FakeGitHub:
    """In-memory stand-in for the handful of GitHub endpoints adoption uses."""
    def __init__(self, files, draft_ok=True):
        self.files, self.draft_ok, self.calls = files, draft_ok, []

    def __call__(self, method, path, token, body=None):
        assert token == TOKEN
        self.calls.append((method, path, body))
        if method == "GET" and path.endswith("/git/ref/heads/main"):
            return 200, {"object": {"sha": BASE}}
        if method == "GET" and path.endswith("/git/commits/" + BASE):
            return 200, {"tree": {"sha": "t" * 40}}
        if method == "GET" and "/contents/" in path:
            name = path.split("/contents/")[1].split("?")[0]
            assert path.endswith("?ref=" + BASE)
            if name not in self.files:
                return 404, {}
            return 200, {"encoding": "base64", "content": base64.encodebytes(self.files[name].encode()).decode()}
        if method == "POST" and path.endswith("/git/trees"):
            return 201, {"sha": "n" * 40}
        if method == "POST" and path.endswith("/git/commits"):
            return 201, {"sha": "c" * 40}
        if method == "POST" and path.endswith("/git/refs"):
            return 201, {}
        if method == "POST" and path.endswith("/pulls"):
            return (201, {"html_url": "https://github.com/acme/basheco/pull/7", "number": 7}) if self.draft_ok else (422, {})
        return 500, {}

    def writes(self):
        return [(m, path.split("/repos/acme/basheco")[1]) for m, path, _ in self.calls if m != "GET"]


def test_patch_applies_cleanly_with_real_git(tmp_path):
    with env(tmp_path) as (root, queue):
        cs = c.create("basheco", operations())
        exported = a.patch(cs["changeset_id"])
        assert exported["applied"] is False and exported["validated_in_isolated_copy"] is False
        assert exported["patch_sha256"] == sha(exported["patch"]) and "\\ No newline at end of file" in exported["patch"]
        repo = tmp_path / "repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / "scripts/a.gd").write_text(OLD)
        (repo / "scripts/b.gd").write_text(OLD)
        file = tmp_path / exported["filename"]
        file.write_text(exported["patch"])
        git = lambda *args: subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
        git("init", "-q")
        git("apply", "--check", str(file))
        git("apply", str(file))
        assert (repo / "scripts/a.gd").read_text() == "extends Node\nvar speed = 3"
        assert (repo / "ui/hud.gd").read_text() == "extends Control\n" and not (repo / "scripts/b.gd").exists()
        assert (root / "scripts/a.gd").read_text() == OLD and (root / "scripts/b.gd").exists() and not (root / "ui").exists()
        (root / "scripts/a.gd").write_text("extends Node\n# moved on\n")
        assert a.patch(cs["changeset_id"])["error"] == "changeset_stale"
        with scope("mcp:read", "owner-2"):
            assert a.patch(cs["changeset_id"])["error"] == "changeset_not_found"


def test_adoption_is_off_until_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_ADOPTION_REPOSITORIES", raising=False)
    monkeypatch.setenv("NEXUS_GITHUB_ADOPTION_TOKEN_FILE", str(tmp_path / "absent"))
    with env(tmp_path) as (root, queue), patch.object(director_requests, "ROOT", queue / "director-requests"):
        cs, _ = validated_changeset(queue)
        status = a.describe()
        assert status["github_enabled"] is False and status["patch_export"] is True and status["merge_enabled"] is False
        assert director_requests.propose_adoption(cs["changeset_id"])["error"] == "adoption_not_configured"
        monkeypatch.setenv("NEXUS_ADOPTION_REPOSITORIES", CONFIG)
        assert director_requests.propose_adoption(cs["changeset_id"])["error"] == "adoption_credentials_missing"
        assert a.patch(cs["changeset_id"])["validated_in_isolated_copy"] is True
    for bad in ('{"basheco":{"repository":"../x"}}', '{"basheco":{"repository":"a/b","base_branch":"nexus/x"}}',
                '{"basheco":{"repository":"a/b","path_prefix":"../etc"}}', '{"BAD":{"repository":"a/b"}}', "not json", "[]"):
        monkeypatch.setenv("NEXUS_ADOPTION_REPOSITORIES", bad)
        assert a.targets() == {}


def test_request_approve_and_publish_draft_pull_request(tmp_path, monkeypatch):
    github = FakeGitHub({"client/scripts/a.gd": OLD, "client/scripts/b.gd": OLD})
    with env(tmp_path) as (root, queue), configured(tmp_path, monkeypatch, queue), patch.object(a, "_github", github):
        unvalidated = c.create("basheco", [operations()[1]])
        assert director_requests.propose_adoption(unvalidated["changeset_id"])["error"] == "validated_pipeline_required"
        cs, pipeline_id = validated_changeset(queue)
        assert TOKEN not in json.dumps(a.describe()) and a.describe()["github_enabled"] is True
        with scope("mcp:read"):
            proposal = director_requests.propose_adoption(cs["changeset_id"], "Ready to review")
            assert proposal["executed"] is False and proposal["repository"] == "acme/basheco"
            assert proposal["repository_paths"] == ["client/scripts/a.gd", "client/ui/hud.gd", "client/scripts/b.gd"]
            assert director_requests.status(proposal["request_id"])["plan_current"] is True
        assert github.calls == []   # proposing never talks to GitHub
        token = principal_var.set(None)
        try:
            with patch.object(director_requests, "current_user", return_value=OWNER):
                detail = director_requests.get(proposal["request_id"], None)
                assert detail["adoption"]["base_branch"] == "main" and len(detail["changeset"]["files"]) == 3
                done = director_requests.review(proposal["request_id"], "approved", None)
        finally:
            principal_var.reset(token)
        result = done["result"]
        assert done["status"] == "completed" and result["pull_request_url"].endswith("/pull/7") and result["draft"] is True
        assert result["branch"].startswith("nexus/adopt-") and result["merged"] is False and result["base_sha"] == BASE
        assert github.writes() == [("POST", "/git/trees"), ("POST", "/git/commits"), ("POST", "/git/refs"), ("POST", "/pulls")]
        tree = next(body for m, path, body in github.calls if path.endswith("/git/trees"))
        assert tree["base_tree"] == "t" * 40 and tree["tree"][2] == {"path": "client/scripts/b.gd", "mode": "100644", "type": "blob", "sha": None}
        assert tree["tree"][1]["content"] == "extends Control\n"
        commit = next(body for m, path, body in github.calls if path.endswith("/git/commits"))
        assert commit["parents"] == [BASE] and pipeline_id in commit["message"] and cs["digest"] in commit["message"]
        ref = next(body for m, path, body in github.calls if path.endswith("/git/refs"))
        assert ref == {"ref": "refs/heads/" + result["branch"], "sha": "c" * 40}
        pull = next(body for m, path, body in github.calls if path.endswith("/pulls"))
        assert pull["draft"] is True and pull["base"] == "main" and pull["head"] == result["branch"]
        assert not any(m in ("PATCH", "PUT", "DELETE") or "/merge" in path for m, path, _ in github.calls)
        assert (root / "scripts/a.gd").read_text() == OLD and not (root / "ui").exists()
        assert "adopted" in (queue / "director-adoptions" / "audit.jsonl").read_text()
        assert TOKEN not in (queue / "director-requests" / (proposal["request_id"] + ".json")).read_text()


def _approve(proposal):
    token = principal_var.set(None)
    try:
        with patch.object(director_requests, "current_user", return_value=OWNER):
            return director_requests.review(proposal["request_id"], "approved", None)
    finally:
        principal_var.reset(token)


def test_repository_must_match_the_validated_source(tmp_path, monkeypatch):
    for files, error in (({"client/scripts/a.gd": "extends Node\n# diverged\n", "client/scripts/b.gd": OLD}, "repository_differs_from_validated_source"),
                         ({"client/scripts/a.gd": OLD}, "repository_file_unavailable"),
                         ({"client/scripts/a.gd": OLD, "client/scripts/b.gd": OLD, "client/ui/hud.gd": "x"}, "already_exists_in_repository")):
        github = FakeGitHub(files)
        work = tmp_path / error
        work.mkdir()
        with env(work) as (root, queue), configured(work, monkeypatch, queue), patch.object(a, "_github", github):
            cs, _ = validated_changeset(queue)
            done = _approve(director_requests.propose_adoption(cs["changeset_id"]))
            assert done["status"] == "failed" and done["result"]["error"] == error
            assert github.writes() == []   # nothing was written to the repository


def test_denied_stale_or_retargeted_requests_publish_nothing(tmp_path, monkeypatch):
    github = FakeGitHub({"client/scripts/a.gd": OLD, "client/scripts/b.gd": OLD})
    with env(tmp_path) as (root, queue), configured(tmp_path, monkeypatch, queue), patch.object(a, "_github", github):
        cs, _ = validated_changeset(queue)
        denied = director_requests.propose_adoption(cs["changeset_id"])
        with patch.object(director_requests, "current_user", return_value=OWNER):
            assert director_requests.review(denied["request_id"], "denied", None)["status"] == "denied"
        retargeted = director_requests.propose_adoption(cs["changeset_id"])
        monkeypatch.setenv("NEXUS_ADOPTION_REPOSITORIES", CONFIG.replace("acme/basheco", "acme/other"))
        assert _approve(retargeted)["result"]["error"] == "adoption_digest_mismatch"
        monkeypatch.setenv("NEXUS_ADOPTION_REPOSITORIES", CONFIG)
        stale = director_requests.propose_adoption(cs["changeset_id"])
        (root / "scripts/a.gd").write_text("extends Node\n# changed\n")
        assert _approve(stale)["result"]["error"] == "changeset_stale"
        assert github.calls == []
        with scope("mcp:read"):
            try:
                a.execute(cs["changeset_id"], "x")
            except PermissionError:
                pass
            else:
                raise AssertionError("execute must require owner write")


def test_branch_stays_when_draft_pull_request_is_unavailable(tmp_path, monkeypatch):
    github = FakeGitHub({"client/scripts/a.gd": OLD, "client/scripts/b.gd": OLD}, draft_ok=False)
    with env(tmp_path) as (root, queue), configured(tmp_path, monkeypatch, queue), patch.object(a, "_github", github):
        cs, _ = validated_changeset(queue)
        done = _approve(director_requests.propose_adoption(cs["changeset_id"]))
        assert done["status"] == "completed" and done["result"]["pull_request_url"] is None
        assert done["result"]["pull_request_error"] == "draft_pull_request_failed" and done["result"]["branch"].startswith("nexus/adopt-")
        assert sum(1 for m, path in github.writes() if path == "/pulls") == 1   # no non-draft fallback


def test_patch_download_endpoint(tmp_path):
    client = TestClient(app)
    assert client.get("/api/director/adoption").status_code == 401
    assert client.get("/api/director/changesets/cs-" + "a" * 32 + "/patch").status_code == 401
    with env(tmp_path) as (root, queue):
        cs = c.create("basheco", operations())
        token = principal_var.set(None)
        try:
            with patch.object(dashboard_director, "current_user", return_value=OWNER):
                response = client.get("/api/director/changesets/" + cs["changeset_id"] + "/patch")
                assert response.status_code == 200 and response.text.startswith("diff --git a/scripts/a.gd b/scripts/a.gd")
                assert "attachment" in response.headers["content-disposition"] and response.headers["cache-control"] == "private, no-store"
                assert client.get("/api/director/changesets/cs-" + "0" * 32 + "/patch").status_code == 404
                assert client.get("/api/director/adoption").json()["writes_live_game_directory"] is False
            with patch.object(dashboard_director, "current_user", return_value={"id": "v", "roles": ["viewer"]}):
                assert client.get("/api/director/changesets/" + cs["changeset_id"] + "/patch").status_code == 403
        finally:
            principal_var.reset(token)
