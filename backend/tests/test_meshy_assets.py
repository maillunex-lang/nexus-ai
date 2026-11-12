from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi import HTTPException
from nexus.main import app
from nexus.meshy_assets import glb_link
from uuid import UUID

RID=UUID("00000000-0000-0000-0000-000000000001")

def test_glb_requires_session():
    client=TestClient(app,base_url="http://localhost")
    assert client.get(f"/api/meshy/requests/{RID}/glb").status_code==401

def test_glb_rejects_viewer():
    with patch("nexus.meshy_assets.owner",side_effect=HTTPException(403,"Owner required")):
        client=TestClient(app,base_url="http://localhost")
        assert client.get(f"/api/meshy/requests/{RID}/glb").status_code==403

def test_glb_link_host_restriction():
    from nexus.meshy_assets import urlsplit
    for link in ["http://assets.meshy.ai/model.glb","https://evil.test/model.glb",
                 "https://assets.meshy.ai.evil.test/model.glb","https://user@assets.meshy.ai/model.glb"]:
        parsed=urlsplit(link)
        allowed=parsed.scheme=="https" and not parsed.username and not parsed.password and (
            parsed.hostname in ("assets.meshy.ai","cdn.meshy.ai","meshy.ai","www.meshy.ai") or
            (parsed.hostname or "").endswith(".meshy.ai"))
        assert not allowed
