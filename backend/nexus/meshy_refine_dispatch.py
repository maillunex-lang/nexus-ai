"""At-most-once, owner-approved Meshy Text-to-3D Refine (2K texture).

Provider docs: https://docs.meshy.ai/en/api/text-to-3d
Pricing: https://docs.meshy.ai/en/api/pricing
No automatic retry of ambiguous paid POST.
"""
import json
import os
import re
import time
from urllib.request import Request,build_opener
from urllib.error import HTTPError,URLError
from uuid import UUID
from fastapi import HTTPException
from .db import connection
from .meshy_reader import _key,NoRedirect,balance,task_status
from .meshy_approvals import owner

REFINE_COST=10
ENDPOINT="https://api.meshy.ai/openapi/v2/text-to-3d"
TASK_ID=re.compile(r"[a-zA-Z0-9-]{8,100}\Z")

def dispatch(request_id:UUID, request):
    user=owner(request)
    if os.environ.get("NEXUS_MESHY_VERIFIED_REFINE_COST")!=str(REFINE_COST):
        raise HTTPException(503,"Refine disabled until operator verifies pricing")
    key=_key()
    if not key:
        raise HTTPException(503,"Meshy API key unavailable")
    with connection() as conn:
        with conn.transaction():
            # Serialize credit-consuming NEXUS dispatches for this DB.
            conn.execute("SELECT pg_advisory_xact_lock(607310)")
            row=conn.execute("""SELECT r.status,r.dispatch_state,r.expires_at,r.max_credits,
                p.provider_task_id,p.dispatch_state
                FROM meshy_refine_requests r
                JOIN meshy_requests p ON p.id=r.preview_request_id
                WHERE r.id=%s AND r.created_by=%s FOR UPDATE OF r""",
                (request_id,user["id"])).fetchone()
            if not row:
                raise HTTPException(404,"Refine request not found")
            status,state,expires,cap,preview_id,preview_state=row
            if status!="approved" or state!="not_started" or expires.timestamp()<=time.time():
                raise HTTPException(409,"Refine not approved, expired or already dispatched")
            if cap<REFINE_COST or preview_state!="submitted" or not preview_id:
                raise HTTPException(409,"Credit ceiling too low or Preview unavailable")
            current=balance()
            available=current.get("balance") if isinstance(current,dict) else None
            if isinstance(available,bool) or not isinstance(available,(int,float)) or available<REFINE_COST:
                raise HTTPException(409,"Insufficient or unknown Meshy balance")
            # Do not start a second NEXUS charge while a paid POST outcome is unresolved.
            busy=conn.execute("""SELECT
                (SELECT count(*) FROM meshy_requests WHERE dispatch_state IN ('dispatching','uncertain'))
                +(SELECT count(*) FROM meshy_refine_requests WHERE dispatch_state IN ('dispatching','uncertain'))""").fetchone()[0]
            if busy:
                raise HTTPException(409,"Another Meshy dispatch has unresolved outcome")
            provider=task_status(preview_id)
            if provider.get("task",{}).get("status")!="SUCCEEDED":
                raise HTTPException(409,"Preview has not succeeded")
            conn.execute("""UPDATE meshy_refine_requests SET dispatch_state='dispatching'
                WHERE id=%s AND dispatch_state='not_started'""",(request_id,))
    # Never automatically repeat this call, even if network fails after provider accepted it.
    payload={"mode":"refine","preview_task_id":preview_id,
             "target_formats":["glb"],"texture_resolution":"2k","enable_pbr":True}
    req=Request(ENDPOINT,data=json.dumps(payload).encode(),method="POST",
                headers={"Authorization":"Bearer "+key,"Content-Type":"application/json",
                         "Accept":"application/json"})
    try:
        with build_opener(NoRedirect()).open(req,timeout=20) as response:
            raw=response.read(4097)
            if len(raw)>4096:
                raise ValueError("Provider response too large")
            task=json.loads(raw).get("result")
            if not isinstance(task,str) or not TASK_ID.fullmatch(task):
                raise ValueError("Invalid provider task ID")
    except (HTTPError,URLError,OSError,ValueError,TimeoutError):
        with connection() as conn:
            conn.execute("""UPDATE meshy_refine_requests SET dispatch_state='uncertain'
                WHERE id=%s AND dispatch_state='dispatching'""",(request_id,))
        return {"id":str(request_id),"status":"uncertain","retry_allowed":False,
                "message":"Check Meshy tasks manually before any further paid dispatch"}
    with connection() as conn:
        conn.execute("""UPDATE meshy_refine_requests SET dispatch_state='submitted',
            provider_task_id=%s WHERE id=%s AND dispatch_state='dispatching'""",
            (task,request_id))
    return {"id":str(request_id),"status":"submitted","task_id":task,
            "estimated_credits":REFINE_COST,"format":"glb"}

def inspect(request_id:UUID,request):
    user=owner(request)
    with connection() as conn:
        row=conn.execute("""SELECT status,dispatch_state,provider_task_id,max_credits
            FROM meshy_refine_requests WHERE id=%s AND created_by=%s""",
            (request_id,user["id"])).fetchone()
    if not row:
        raise HTTPException(404,"Refine request not found")
    result={"id":str(request_id),"approval_status":row[0],
            "dispatch_state":row[1],"provider_task_id":row[2],
            "max_credits":row[3]}
    if row[2]:
        result["provider"]=task_status(row[2])
    return result
