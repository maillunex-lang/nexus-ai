"""Meshy API read-only connector, disabled until server-side key configured.

Never sends POST, exposes credentials, or starts paid tasks.
"""
import os
import json
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

BASE = "https://api.meshy.ai"
MAX_BYTES = 160_000
SECRET_PATH = "/run/secrets/meshy_api_key"


def _key():
    """Read a Docker-mounted secret without putting it in container environment."""
    try:
        with open(SECRET_PATH, "r", encoding="utf-8") as stream:
            return stream.read(256).strip()
    except (OSError, UnicodeError):
        return ""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _configured():
    return bool(_key())


def connection_status():
    return {"provider": "meshy", "configured": _configured(),
            "mode": "read_only", "generation_enabled": False,
            "billing_actions_enabled": False,
            "requires_separate_api_credits": True}


def _get(path):
    key = _key()
    if not key:
        return {"error": "meshy_not_configured"}
    request = Request(BASE + path, method="GET", headers={
        "Authorization": "Bearer " + key,
        "Accept": "application/json",
        "User-Agent": "NEXUS-AI-Meshy-readonly/6.1"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            if response.status != 200:
                return {"error": "meshy_upstream_error"}
            payload = response.read(MAX_BYTES + 1)
            if len(payload) > MAX_BYTES:
                return {"error": "meshy_response_too_large"}
            return json.loads(payload)
    except HTTPError as exc:
        return {"error": {401: "meshy_invalid_key", 402: "meshy_payment_required",
                          403: "meshy_access_denied", 429: "meshy_rate_limited"}.get(
                              exc.code, "meshy_upstream_error")}
    except (URLError, OSError, ValueError, TimeoutError):
        return {"error": "meshy_unavailable"}


def balance():
    result = _get("/openapi/v1/balance")
    if not isinstance(result, dict) or "error" in result:
        return result if isinstance(result, dict) else {"error": "invalid_response"}
    return {"balance": result.get("balance"), "monthly_credits": result.get("monthly_credits"),
            "permanent_credits": result.get("permanent_credits"),
            "monthly_resets_at": result.get("monthly_resets_at"),
            "source": "meshy_api", "read_only": True}


def _task_summary(task):
    if not isinstance(task, dict):
        return None
    return {k: task.get(k) for k in ("id", "type", "status", "progress", "created_at",
                                     "finished_at", "consumed_credits")}


def text_tasks():
    result = _get("/openapi/v2/text-to-3d?page_size=10")
    if isinstance(result, dict) and "error" in result:
        return result
    if not isinstance(result, list):
        return {"error": "invalid_response"}
    return {"tasks": [x for task in result[:10] if (x := _task_summary(task)) is not None],
            "read_only": True, "generation_enabled": False}

def task_status(task_id: str):
    """Read one provider task, without leaking signed download URLs."""
    import re
    if not isinstance(task_id, str) or not re.fullmatch(r"[a-zA-Z0-9-]{8,100}", task_id):
        return {"error": "invalid_task_id"}
    result = _get("/openapi/v2/text-to-3d/" + task_id)
    if isinstance(result, dict) and "error" in result:
        return result
    summary = _task_summary(result)
    if summary is None:
        return {"error": "invalid_response"}
    return {"task": summary, "glb_available": bool(
        isinstance(result.get("model_urls"), dict) and result["model_urls"].get("glb")),
        "read_only": True}
