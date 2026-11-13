"""Stage 6: Mission Control links, retention and the optional schedule."""
import asyncio
import json
import os
import time
from contextlib import contextmanager
from unittest.mock import patch
from fastapi.testclient import TestClient
from nexus import dashboard_director, director_requests
from nexus import director_pipelines as p
from nexus import director_retention as r
from nexus import director_scheduler as sched
from nexus import director_settings
from nexus import director_task_links as links
from nexus.main import app
from nexus.mcp_principal import principal_var
from test_director_pipelines import env, changeset, host_finish, stage

OWNER = "11111111-1111-4111-8111-111111111111"
TASK = "22222222-2222-4222-8222-222222222222"


class FakeDb:
    def __init__(self, task_exists=True, fail=False):
        self.task_exists, self.fail, self.writes = task_exists, fail, []

    @contextmanager
    def connection(self):
        if self.fail:
            raise RuntimeError("database down")
        yield self

    def execute(self, sql, params=()):
        if sql.startswith("SELECT"):
            row = ("33333333-3333-4333-8333-333333333333", "Ускорить игрока", "in_progress") if self.task_exists else None
            return type("Cursor", (), {"fetchone": lambda _: row})()
        self.writes.append((sql.split("(")[0].split()[-1], params[-1] if params else None))


def task_events(db):
    return [value for table, value in db.writes if table == "mission_task_events"]


def test_pipeline_milestones_are_written_to_the_linked_task(tmp_path):
    db = FakeDb()
    with env(tmp_path, user=OWNER) as (root, queue), patch.object(links, "connection", db.connection):
        view = p.launch("build_apk", "basheco", task_id=TASK)
        assert view["task_id"] == TASK and task_events(db) == ["director.pipeline.started"]
        assert p.list_pipelines(task_id=TASK)["pipelines"][0]["pipeline_id"] == view["pipeline_id"]
        assert p.list_pipelines(task_id="44444444-4444-4444-8444-444444444444")["pipelines"] == []
        host_finish(queue, "build_pending", "build_failed", stage(view, "build")["job_id"], {"passed": False, "error": "build_failed"})
        assert p.status(view["pipeline_id"])["state"] == "failed"
        p.status(view["pipeline_id"])
        assert task_events(db) == ["director.pipeline.started", "director.pipeline.failed"]
        retried = p.retry(view["pipeline_id"])
        host_finish(queue, "build_pending", "build_completed", stage(retried, "build")["job_id"],
                    {"passed": True, "bytes": 1, "sha256": "a" * 64})
        assert p.status(view["pipeline_id"])["state"] == "completed"
        assert task_events(db)[2:] == ["director.pipeline.retried", "director.pipeline.completed"]
        other = p.launch("build_apk", "basheco", task_id=TASK)
        p.cancel(other["pipeline_id"])
        assert task_events(db)[-1] == "director.pipeline.cancelled"
        assert p._digest("build_apk", "basheco", "", "") == view["plan_digest"]  # the link is not part of the plan


def test_unknown_task_or_database_outage(tmp_path):
    with env(tmp_path, user=OWNER) as (root, queue):
        with patch.object(links, "connection", FakeDb(task_exists=False).connection):
            assert p.launch("build_apk", "basheco", task_id=TASK)["error"] == "task_not_found"
            assert p.launch("build_apk", "basheco", task_id="not-a-uuid")["error"] == "invalid_task_id"
        with patch.object(links, "connection", FakeDb(fail=True).connection):
            assert p.launch("build_apk", "basheco", task_id=TASK)["error"] == "task_storage_unavailable"
        assert not (queue / "director-pipelines").exists()
        db = FakeDb()
        with patch.object(links, "connection", db.connection):
            view = p.launch("build_apk", "basheco", task_id=TASK)
        with patch.object(links, "connection", FakeDb(fail=True).connection):  # outage mid-run
            host_finish(queue, "build_pending", "build_completed", stage(view, "build")["job_id"],
                        {"passed": True, "bytes": 1, "sha256": "a" * 64})
            assert p.status(view["pipeline_id"])["state"] == "completed"
        assert links.record(TASK, "not-a-uuid", "started") is False and links.record(TASK, OWNER, "invented") is False


def test_approval_request_carries_the_task_link(tmp_path):
    db = FakeDb()
    with env(tmp_path, scope="mcp:read", user=OWNER) as (root, queue), patch.object(links, "connection", db.connection), \
         patch.object(director_requests, "ROOT", queue / "director-requests"):
        assert director_requests.propose_pipeline("build_apk", "basheco", "", "", "bad")["error"] == "invalid_task_id"
        proposal = director_requests.propose_pipeline("build_apk", "basheco", "", "", TASK)
        assert db.writes == []
        with patch.object(director_requests, "current_user", return_value={"id": OWNER, "roles": ["owner"]}):
            approved = director_requests.review(proposal["request_id"], "approved", None)
        assert approved["pipeline_state"]["task_id"] == TASK and task_events(db) == ["director.pipeline.started"]


def _age(path, days):
    data = json.loads(path.read_text())
    stamp = "2020-01-01T00:00:00+00:00"
    data.update({key: stamp for key in ("created_at", "finished_at", "updated_at") if key in data})
    path.write_text(json.dumps(data))
    os.utime(path, (time.time() - days * 86400,) * 2)


def test_retention_removes_only_old_finished_director_state(tmp_path):
    with env(tmp_path) as (root, queue), patch.object(r, "QUEUE", queue), patch.object(director_requests, "ROOT", queue / "director-requests"):
        pipes = queue / "director-pipelines"
        old_done = p.launch("project_audit", "basheco")
        fresh_done = p.launch("project_audit", "basheco")
        old_running = p.launch("build_apk", "basheco")
        used = changeset()
        old_with_changes = p.launch("change_validate", "basheco", used["changeset_id"])
        orphan = changeset(content="extends Node\nvar orphan = 1\n")
        pending = changeset(content="extends Node\nvar pending = 1\n")
        fresh = changeset(content="extends Node\nvar fresh = 1\n")
        with principal_var_scope("mcp:read"):
            request = director_requests.propose_pipeline("change_validate", "basheco", pending["changeset_id"])
        for view in (old_done, old_running, old_with_changes):
            _age(pipes / (view["pipeline_id"] + ".json"), 90)
        for item in (used, orphan, pending):
            _age(queue / "director-changesets" / (item["changeset_id"] + ".json"), 90)
        archive = queue / "director-errors" / "abc.jsonl.1"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text("{}\n")
        os.utime(archive, (time.time() - 90 * 86400,) * 2)
        (queue / "director-errors" / "abc.jsonl").write_text("{}\n")
        stale_lock = pipes / "locks" / "pipe-x.lock"
        stale_lock.parent.mkdir(exist_ok=True)
        stale_lock.write_text("")
        os.utime(stale_lock, (time.time() - 2 * 86400,) * 2)
        build_job = queue / "build_pending" / (stage(old_running, "build")["job_id"] + ".json")

        assert r.purge(days=0)["disabled"] is True and (pipes / (old_done["pipeline_id"] + ".json")).exists()
        result = r.purge(days=30)
        assert result == {"retention_days": 30, "pipelines": 1, "changesets": 1, "error_archives": 1, "locks": 1}
        assert not (pipes / (old_done["pipeline_id"] + ".json")).exists()
        assert not (pipes / "events" / (old_done["pipeline_id"] + ".jsonl")).exists()
        for kept in (fresh_done, old_running, old_with_changes):   # recent, or still running
            assert (pipes / (kept["pipeline_id"] + ".json")).exists()
        remaining = {path.stem for path in (queue / "director-changesets").glob("cs-*.json")}
        assert remaining == {used["changeset_id"], pending["changeset_id"], fresh["changeset_id"]}
        assert build_job.exists() and (queue / "director-requests" / (request["request_id"] + ".json")).exists()
        assert (queue / "director-errors" / "abc.jsonl").exists() and (root / "scripts/a.gd").exists()
        assert r.purge(days=30)["pipelines"] == 0


@contextmanager
def principal_var_scope(scope):
    current = principal_var.get()
    token = principal_var.set({**current, "scope": scope})
    try:
        yield
    finally:
        principal_var.reset(token)


def test_retention_and_schedule_configuration(monkeypatch):
    for value, expected in (("", 30), ("7", 7), ("0", 0), ("-1", 30), ("junk", 30), ("99999", 30)):
        monkeypatch.setenv("NEXUS_DIRECTOR_RETENTION_DAYS", value)
        assert r.retention_days() == expected
    for value, expected in (("", 0), ("60", 60), ("5", 0), ("999999", 0), ("abc", 0)):
        monkeypatch.setenv("NEXUS_DIRECTOR_TICK_SECONDS", value)
        assert sched.interval() == expected


def test_schedule_is_off_by_default_and_survives_failures(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_DIRECTOR_TICK_SECONDS", raising=False)

    async def started():
        return sched.start()
    assert asyncio.run(started()) is None
    with env(tmp_path) as (root, queue), patch.object(r, "QUEUE", queue):
        view = p.launch("build_apk", "basheco")
        host_finish(queue, "build_pending", "build_completed", stage(view, "build")["job_id"],
                    {"passed": True, "bytes": 1, "sha256": "a" * 64})
        token = principal_var.set(None)
        try:
            with patch.object(sched, "_last_retention", 0.0):
                first = sched.run_once()
                assert first["tick"] == {"examined": 1, "advanced": 1} and first["retention"]["retention_days"] == 30
                assert "retention" not in sched.run_once()   # at most once an hour
            with patch.object(sched, "tick", side_effect=RuntimeError("boom")), patch.object(sched, "_last_retention", 0.0), \
                 patch.object(sched, "purge", side_effect=OSError("disk")):
                assert sched.run_once() == {"tick_error": "RuntimeError", "retention_error": "OSError"}
        finally:
            principal_var.reset(token)
        assert p.status(view["pipeline_id"])["state"] == "completed"

    async def one_pass():
        calls = []
        with patch.object(sched, "run_once", side_effect=lambda: calls.append(1)), \
             patch.object(sched.asyncio, "sleep", side_effect=[None, asyncio.CancelledError()]):
            try:
                await sched.loop(15)
            except asyncio.CancelledError:
                pass
        return calls
    assert asyncio.run(one_pass()) == [1]


def test_settings_endpoints_are_owner_session_only(tmp_path):
    client = TestClient(app)
    assert client.get("/api/director/settings").status_code == 401
    assert client.post("/api/director/settings/change-validation", json={"project_id": "watermmo", "enabled": True}).status_code == 401
    entries = {"basheco": {"name": "B"}, "watermmo": {"name": "W"}}
    with patch.object(director_settings, "ROOT", tmp_path / "settings"), patch.object(director_settings, "PROJECTS", entries):
        with patch.object(dashboard_director, "current_user", return_value={"id": "op", "roles": ["operator"]}):
            assert client.post("/api/director/settings/change-validation", json={"project_id": "watermmo", "enabled": True}).status_code == 403
        with patch.object(dashboard_director, "current_user", return_value={"id": OWNER, "roles": ["owner"]}):
            body = {"project_id": "watermmo", "enabled": True}
            assert client.post("/api/director/settings/change-validation", json=body, headers={"sec-fetch-site": "cross-site"}).status_code == 403
            assert client.post("/api/director/settings/change-validation", json={"project_id": "watermmo", "enabled": "maybe"}).status_code == 422
            enabled = client.post("/api/director/settings/change-validation", json=body).json()
            assert {x["project_id"]: x["enabled"] for x in enabled["change_validation"]} == {"basheco": True, "watermmo": True}
            assert client.get("/api/director/settings").json()["change_validation"][0]["locked"] is True
