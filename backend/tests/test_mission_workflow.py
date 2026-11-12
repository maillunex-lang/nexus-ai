from uuid import uuid4
from fastapi.testclient import TestClient
from nexus.main import app
from nexus.mission_workflow import ProjectCreate,TaskCreate,TaskUpdate,TRANSITIONS


def test_mutations_require_login():
    c=TestClient(app)
    assert c.post("/api/mission/projects",json={"name":"Example project"}).status_code==401
    assert c.post("/api/mission/tasks",json={"project_id":str(uuid4()),"title":"Example task"}).status_code==401
    assert c.patch("/api/mission/tasks/"+str(uuid4()),json={"status":"ready","version":1}).status_code==401

def test_cross_site_project_mutation_rejected():
    r=TestClient(app).post("/api/mission/projects",headers={"Sec-Fetch-Site":"cross-site"},json={"name":"Example project"})
    assert r.status_code==403

def test_viewer_cannot_write(monkeypatch):
    monkeypatch.setattr("nexus.mission_workflow.current_user",lambda request:{"id":str(uuid4()),"roles":["viewer"]})
    r=TestClient(app).post("/api/mission/projects",json={"name":"Example project"})
    assert r.status_code==403

def test_state_machine_blocks_terminal_reopening():
    assert TRANSITIONS["done"]==set()
    assert TRANSITIONS["cancelled"]==set()
    assert "done" not in TRANSITIONS["backlog"]
    assert "in_progress" in TRANSITIONS["ready"]

def test_invalid_payload_rejected():
    c=TestClient(app)
    assert c.post("/api/mission/projects",json={"name":"x"}).status_code==422
    assert c.post("/api/mission/tasks",json={"project_id":"bad","title":"abc"}).status_code==422

def test_director_plan_requires_login():
    assert TestClient(app).get("/api/mission/tasks/"+str(uuid4())+"/director-plan").status_code==401
