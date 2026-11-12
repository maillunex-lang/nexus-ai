from fastapi.testclient import TestClient
from nexus.main import app


def test_mission_requires_login():
    client = TestClient(app)
    response = client.get("/api/mission/overview")
    assert response.status_code == 401


def test_mission_requires_role(monkeypatch):
    from nexus import mission
    monkeypatch.setattr(mission, "current_user", lambda request: {"id": "abc", "roles": [], "username": "test"})
    client = TestClient(app)
    response = client.get("/api/mission/overview")
    assert response.status_code == 403


def test_mission_returns_read_only_data(monkeypatch):
    from nexus import mission
    from contextlib import contextmanager

    class FakeCursor:
        def __init__(self, rows):
            self.rows = rows
        def fetchall(self):
            return self.rows

    class FakeConn:
        def execute(self, query):
            if "FROM projects" in query:
                return FakeCursor([])
            if "FROM approval_requests" in query:
                return FakeCursor([("pending", 2)])
            if "FROM audit_events" in query:
                return FakeCursor([])
            raise AssertionError(query)

    @contextmanager
    def fake_connection():
        yield FakeConn()

    monkeypatch.setattr(mission, "current_user", lambda request: {"id": "abc", "roles": ["owner"], "username": "test"})
    monkeypatch.setattr(mission, "connection", fake_connection)
    client = TestClient(app)
    response = client.get("/api/mission/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["projects"] == []
    assert body["approvals"] == [{"status": "pending", "count": 2}]
    assert body["read_only"] is True
    assert body["capabilities"]["task_execution"] is False
