from fastapi.testclient import TestClient
from pydantic import ValidationError
from nexus.main import app
from nexus.meshy_refine import RefineCreate, RefineReview

RID="00000000-0000-0000-0000-000000000001"

def test_refine_requires_session():
    c=TestClient(app,base_url="http://localhost")
    assert c.post("/api/meshy/refine",json={"preview_request_id":RID,"max_credits":10}).status_code==401
    assert c.post(f"/api/meshy/refine/{RID}/review",json={"decision":"approve"}).status_code==401
    assert c.get(f"/api/meshy/refine/{RID}").status_code==401

def test_refine_cross_site_blocked():
    c=TestClient(app,base_url="http://localhost")
    assert c.post("/api/meshy/refine",headers={"sec-fetch-site":"cross-site"},
                  json={"preview_request_id":RID,"max_credits":10}).status_code==403

def test_refine_credit_floor():
    try:
        RefineCreate(preview_request_id=RID,max_credits=9)
        assert False
    except ValidationError:
        pass
    assert RefineCreate(preview_request_id=RID,max_credits=10).max_credits==10

def test_refine_decision_validation():
    try:
        RefineReview(decision="dispatch")
        assert False
    except ValidationError:
        pass
