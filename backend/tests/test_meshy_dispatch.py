from unittest.mock import patch
from fastapi.testclient import TestClient
from nexus.main import app
from nexus.meshy_dispatch import PREVIEW_COST
from nexus.meshy_reader import task_status

def test_preview_cost():
    assert PREVIEW_COST == 20

def test_dispatch_requires_session():
    client=TestClient(app,base_url="http://localhost")
    assert client.post("/api/meshy/requests/00000000-0000-0000-0000-000000000001/dispatch").status_code==401
    assert client.get("/api/meshy/requests/00000000-0000-0000-0000-000000000001/status").status_code==401

def test_dispatch_cross_site_rejected():
    client=TestClient(app,base_url="http://localhost")
    result=client.post("/api/meshy/requests/00000000-0000-0000-0000-000000000001/dispatch",
       headers={"sec-fetch-site":"cross-site"})
    assert result.status_code==403

def test_task_status_sanitized():
    with patch("nexus.meshy_reader._get",return_value={"id":"12345678","status":"SUCCEEDED",
       "progress":100,"prompt":"secret","model_urls":{"glb":"https://private/?token=secret"}}):
        result=task_status("12345678")
    assert result["glb_available"] is True
    assert "secret" not in str(result)

def test_task_status_rejects_injection():
    assert task_status("../secret")["error"]=="invalid_task_id"
