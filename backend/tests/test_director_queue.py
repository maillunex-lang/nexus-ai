from uuid import uuid4
from fastapi.testclient import TestClient
from nexus.main import app

def test_queue_routes_require_login():
    c=TestClient(app)
    assert c.post(f"/api/mission/proposals/{uuid4()}/enqueue").status_code==401
    assert c.get(f"/api/mission/projects/{uuid4()}/jobs").status_code==401
    assert c.post(f"/api/mission/jobs/{uuid4()}/cancel").status_code==401

def test_queue_rejects_cross_site_request():
    c=TestClient(app)
    assert c.post(f"/api/mission/proposals/{uuid4()}/enqueue",
        headers={"Sec-Fetch-Site":"cross-site"}).status_code==403

def test_viewer_cannot_enqueue(monkeypatch):
    monkeypatch.setattr("nexus.mission_workflow.current_user",lambda r:{"id":str(uuid4()),"roles":["viewer"]})
    assert TestClient(app).post(f"/api/mission/proposals/{uuid4()}/enqueue").status_code==403

def test_worker_import_does_not_run_jobs():
    from nexus.director_worker import process_one
    assert callable(process_one)
