from unittest.mock import patch
from fastapi.testclient import TestClient
from nexus.main import app
from nexus.identity import current_user
from nexus.meshy_approvals import MeshyRequest

def test_approval_endpoints_reject_unauthenticated():
    c=TestClient(app,base_url="http://localhost")
    assert c.get("/api/meshy/requests").status_code==401
    assert c.post("/api/meshy/requests",json={"prompt":"A realistic farm tractor","max_credits":20}).status_code==401

def test_approval_endpoints_reject_viewer():
    with patch("nexus.meshy_approvals.current_user", return_value={"id":"test","roles":["viewer"],"username":"viewer"}):
        c=TestClient(app,base_url="http://localhost")
        assert c.get("/api/meshy/requests").status_code==403
        assert c.post("/api/meshy/requests",json={"prompt":"A realistic farm tractor","max_credits":20}).status_code==403

def test_approval_input_limits():
    assert MeshyRequest(prompt="A realistic farm tractor",max_credits=1).max_credits==1
    from pydantic import ValidationError
    try:
        MeshyRequest(prompt="A realistic farm tractor",max_credits=1001)
        assert False
    except ValidationError:
        pass

def test_cross_site_write_rejected():
    c=TestClient(app,base_url="http://localhost")
    result=c.post("/api/meshy/requests",headers={"sec-fetch-site":"cross-site"},
      json={"prompt":"A realistic farm tractor","max_credits":20})
    assert result.status_code==403
