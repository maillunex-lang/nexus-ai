from fastapi.testclient import TestClient
from nexus.main import app
from nexus.identity import current_user


def test_protected_apis_require_session():
    client = TestClient(app, base_url="http://localhost")
    assert client.get("/api/operator/overview").status_code == 401
    assert client.get("/api/admin/overview").status_code == 401


def test_viewer_cannot_access_owner_api():
    app.dependency_overrides[current_user] = lambda: {"id": "test", "username": "viewer", "roles": ["viewer"]}
    try:
        client = TestClient(app, base_url="http://localhost")
        assert client.get("/api/operator/overview").status_code == 200
        assert client.get("/api/admin/overview").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_owner_can_access_owner_api():
    app.dependency_overrides[current_user] = lambda: {"id": "test", "username": "owner", "roles": ["owner"]}
    try:
        client = TestClient(app, base_url="http://localhost")
        assert client.get("/api/admin/overview").status_code == 200
    finally:
        app.dependency_overrides.clear()
