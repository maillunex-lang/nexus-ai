"""Owner-approved, at-most-once Meshy 7.1 preview dispatch.

Never retries an uncertain POST. Refine is a separate paid operation, not implemented here.
"""
import json
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError
from uuid import UUID
from fastapi import HTTPException, Request as FastRequest
from .db import connection
from .meshy_approvals import owner
from .meshy_reader import _key, NoRedirect, balance, task_status

PREVIEW_COST = 20
ENDPOINT = "https://api.meshy.ai/openapi/v2/text-to-3d"


def dispatch(request_id: UUID, request: FastRequest):
    user = owner(request)
    # Check API credit balance before reserving the request. This is advisory;
    # an account may be used elsewhere concurrently.
    current = balance()
    if "error" in current:
        raise HTTPException(503, "Meshy balance unavailable")
    available = current.get("balance")
    if isinstance(available, bool) or not isinstance(available, (int, float)) or available < PREVIEW_COST:
        raise HTTPException(409, "Insufficient or unknown API balance")
    with connection() as conn:
        with conn.transaction():
            row = conn.execute("""SELECT proposal,max_credits,status,expires_at,dispatch_state
              FROM meshy_requests WHERE id=%s AND created_by=%s FOR UPDATE""",
              (request_id,user["id"])).fetchone()
            if not row:
                raise HTTPException(404,"Request not found")
            proposal,cap,status,expires,state = row
            if status != "approved" or state != "not_started" or expires.timestamp() <= __import__("time").time():
                raise HTTPException(409,"Not approved, expired or already dispatched")
            if cap < PREVIEW_COST or proposal.get("mode") != "preview":
                raise HTTPException(409,"Credit ceiling too low or unsupported mode")
            conn.execute("""UPDATE meshy_requests SET dispatch_state='dispatching',
              dispatch_started_at=now() WHERE id=%s""",(request_id,))
    # From here, even transport failures are treated as uncertain to prevent
    # duplicate paid generation if Meshy received the request.
    key = _key()
    if not key:
        _mark_uncertain(request_id,"key_unavailable")
        return {"id":str(request_id),"status":"uncertain","error":"key_unavailable"}
    payload = {"mode":"preview","prompt":proposal["prompt"],"ai_model":"meshy-7.1",
               "target_formats":["glb"],"moderation":True}
    req = Request(ENDPOINT, data=json.dumps(payload).encode("utf-8"), method="POST",
                  headers={"Authorization":"Bearer "+key,"Content-Type":"application/json",
                           "Accept":"application/json"})
    try:
        with build_opener(NoRedirect()).open(req,timeout=20) as response:
            data = response.read(4097)
            if len(data)>4096:
                raise ValueError("Response too large")
            result=json.loads(data)
            task_id=result.get("result")
            if not isinstance(task_id,str) or not (8<=len(task_id)<=100) or not all(
                    c.isascii() and (c.isalnum() or c=="-") for c in task_id):
                raise ValueError("Missing provider task id")
    except (HTTPError,URLError,OSError,ValueError,TimeoutError):
        _mark_uncertain(request_id,"provider_outcome_unknown")
        return {"id":str(request_id),"status":"uncertain","retry_allowed":False,
                "message":"Provider outcome unknown; inspect Meshy tasks before any new request"}
    with connection() as conn:
        conn.execute("""UPDATE meshy_requests SET dispatch_state='submitted',
          provider_task_id=%s WHERE id=%s AND dispatch_state='dispatching'""",
          (task_id,request_id))
    return {"id":str(request_id),"status":"submitted","task_id":task_id,
            "estimated_credits":PREVIEW_COST,"refine_started":False}


def _mark_uncertain(request_id,code):
    with connection() as conn:
        conn.execute("""UPDATE meshy_requests SET dispatch_state='uncertain',error_code=%s
          WHERE id=%s AND dispatch_state='dispatching'""",(code,request_id))


def inspect(request_id: UUID, request: FastRequest):
    user=owner(request)
    with connection() as conn:
        row=conn.execute("""SELECT status,dispatch_state,provider_task_id,error_code
          FROM meshy_requests WHERE id=%s AND created_by=%s""",(request_id,user["id"])).fetchone()
    if not row:
        raise HTTPException(404,"Request not found")
    status,state,task_id,error=row
    result={"id":str(request_id),"approval_status":status,"dispatch_state":state,
            "task_id":task_id,"error_code":error}
    if task_id:
        result["provider"]=task_status(task_id)
    return result
