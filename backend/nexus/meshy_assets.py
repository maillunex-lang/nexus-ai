"""Owner-scoped retrieval of finished Meshy GLB asset links.

Never fetches untrusted URLs from the backend. Returns the provider's short-lived
HTTPS link only to an authenticated owner, with no-store headers at the API layer.
"""
from uuid import UUID
from urllib.parse import urlsplit
from fastapi import HTTPException, Request
from .db import connection
from .meshy_approvals import owner
from .meshy_reader import _get

def glb_link(request_id: UUID, request: Request):
    user = owner(request)
    with connection() as conn:
        row=conn.execute("""SELECT provider_task_id,dispatch_state FROM meshy_requests
          WHERE id=%s AND created_by=%s""",(request_id,user["id"])).fetchone()
    if not row:
        raise HTTPException(404,"Request not found")
    if row[1]!="submitted" or not row[0]:
        raise HTTPException(409,"Model not submitted")
    task=_get("/openapi/v2/text-to-3d/"+row[0])
    if not isinstance(task,dict) or "error" in task:
        raise HTTPException(502,"Meshy status unavailable")
    if task.get("status")!="SUCCEEDED":
        raise HTTPException(409,"Model not finished")
    urls=task.get("model_urls")
    link=urls.get("glb") if isinstance(urls,dict) else None
    if not isinstance(link,str) or len(link)>4096:
        raise HTTPException(502,"GLB link unavailable")
    parsed=urlsplit(link)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or parsed.port or parsed.fragment:
        raise HTTPException(502,"Invalid provider link")
    if parsed.hostname.lower() not in ("assets.meshy.ai","cdn.meshy.ai","meshy.ai","www.meshy.ai") and not parsed.hostname.lower().endswith(".meshy.ai"):
        raise HTTPException(502,"Untrusted provider asset host")
    return {"request_id":str(request_id),"glb_url":link,"format":"glb",
            "note":"Short-lived provider link. Do not publish it.","godot_optimized":False}
