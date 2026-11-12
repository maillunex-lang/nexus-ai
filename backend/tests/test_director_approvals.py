from uuid import uuid4
from fastapi.testclient import TestClient
from nexus.main import app
from nexus.director_approvals import plan_for

def test_proposal_endpoints_require_authentication():
    c=TestClient(app)
    assert c.post("/api/mission/tasks/"+str(uuid4())+"/proposals").status_code==401
    assert c.get("/api/mission/projects/"+str(uuid4())+"/proposals").status_code==401
    assert c.post("/api/mission/proposals/"+str(uuid4())+"/review",json={"decision":"approved"}).status_code==401

def test_review_rejects_invalid_decisions():
    c=TestClient(app)
    assert c.post("/api/mission/proposals/"+str(uuid4())+"/review",json={"decision":"execute"}).status_code==422

def test_proposal_creation_blocks_cross_site_requests():
    c=TestClient(app)
    assert c.post("/api/mission/tasks/"+str(uuid4())+"/proposals",
                  headers={"Sec-Fetch-Site":"cross-site"}).status_code==403

def test_director_template_never_executes():
    p=plan_for("Check build","No changes to other projects")
    assert p["execution_enabled"] is False
    assert p["model"]=="template-v1"
    assert all(step["kind"]!="execute" for step in p["steps"])

def test_viewer_cannot_propose(monkeypatch):
    monkeypatch.setattr("nexus.director_approvals.current_user",lambda r:None,raising=False)
    monkeypatch.setattr("nexus.mission_workflow.current_user",lambda r:{"id":str(uuid4()),"roles":["viewer"]})
    assert TestClient(app).post("/api/mission/tasks/"+str(uuid4())+"/proposals").status_code==403
