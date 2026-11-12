from unittest.mock import patch
from fastapi.testclient import TestClient
from nexus.main import app
from nexus.identity import current_user


def test_meshy_routes_require_auth():
    client = TestClient(app, base_url="http://localhost")
    assert client.get("/api/meshy/balance").status_code == 401
    assert client.get("/api/meshy/tasks").status_code == 401


def test_meshy_routes_reject_non_owner():
    app.dependency_overrides[current_user] = lambda: {"id": "test", "username": "viewer", "roles": ["viewer"]}
    try:
        client = TestClient(app, base_url="http://localhost")
        assert client.get("/api/meshy/balance").status_code == 403
        assert client.get("/api/meshy/tasks").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_meshy_routes_owner_read_only():
    app.dependency_overrides[current_user] = lambda: {"id": "test", "username": "owner", "roles": ["owner"]}
    try:
        client = TestClient(app, base_url="http://localhost")
        with patch("nexus.meshy_reader.balance", return_value={"balance": 20}) as balance:
            assert client.get("/api/meshy/balance").json() == {"balance": 20}
            balance.assert_called_once()
        with patch("nexus.meshy_reader.text_tasks", return_value={"tasks": []}) as tasks:
            assert client.get("/api/meshy/tasks").json() == {"tasks": []}
            tasks.assert_called_once()
    finally:
        app.dependency_overrides.clear()
