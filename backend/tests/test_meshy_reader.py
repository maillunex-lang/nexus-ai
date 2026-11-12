from unittest.mock import patch
from nexus import meshy_reader as m

def test_no_key_fails_closed():
    with patch.dict("os.environ", {}, clear=True):
        assert m.connection_status()["configured"] is False
        assert m.balance()["error"] == "meshy_not_configured"
        assert m.text_tasks()["error"] == "meshy_not_configured"

def test_status_does_not_leak_key():
    with patch.dict("os.environ", {"NEXUS_MESHY_API_KEY": "very-secret-key"}):
        assert "very-secret-key" not in str(m.connection_status())
        assert m.connection_status()["generation_enabled"] is False

def test_balance_filter():
    with patch.object(m, "_get", return_value={"balance": 50, "monthly_credits": 30,
               "permanent_credits": 20, "monthly_resets_at": None, "token": "secret"}):
        data=m.balance()
        assert data["balance"] == 50
        assert "token" not in data

def test_tasks_filter():
    with patch.object(m, "_get", return_value=[{"id": "abc", "status": "SUCCEEDED",
                                                  "prompt": "private", "model_urls": {"glb": "secret"}}]):
        result=m.text_tasks()
        assert result["tasks"][0]["id"] == "abc"
        assert "private" not in str(result)
        assert "secret" not in str(result)

def test_error_translation_and_no_redirect():
    from urllib.error import HTTPError
    with patch.dict("os.environ", {"NEXUS_MESHY_API_KEY": "secret"}):
        with patch.object(m, "build_opener") as opener:
            opener.return_value.open.side_effect=HTTPError("url", 401, "unauthorized", None, None)
            assert m.balance()["error"] == "meshy_invalid_key"
    assert m.NoRedirect().redirect_request(None,None,302,"redirect",{},"https://other") is None
