"""Separate explicit approval for Meshy texture refinement.

Refine dispatch is disabled until provider request/cost contracts are verified.
"""
from uuid import UUID
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from typing import Literal
from .db import connection
from .meshy_approvals import owner
from .meshy_reader import task_status

class RefineCreate(BaseModel):
    preview_request_id: UUID
    max_credits: int = Field(ge=10, le=1000)

class RefineReview(BaseModel):
    decision: Literal["approve","reject"]

def create(payload: RefineCreate, request: Request):
    user=owner(request)
    with connection() as conn:
        with conn.transaction():
            row=conn.execute("""SELECT provider_task_id,dispatch_state FROM meshy_requests
              WHERE id=%s AND created_by=%s""",(payload.preview_request_id,user["id"])).fetchone()
            if not row or row[1]!="submitted" or not row[0]:
                raise HTTPException(409,"Preview not submitted")
            status=task_status(row[0])
            if status.get("task",{}).get("status")!="SUCCEEDED":
                raise HTTPException(409,"Preview not completed")
            result=conn.execute("""INSERT INTO meshy_refine_requests
              (preview_request_id,created_by,max_credits) VALUES (%s,%s,%s)
              ON CONFLICT (preview_request_id) DO NOTHING RETURNING id,expires_at""",
              (payload.preview_request_id,user["id"],payload.max_credits)).fetchone()
            if not result:
                raise HTTPException(409,"Refine request already exists")
    return {"id":str(result[0]),"status":"pending","expires_at":result[1].isoformat(),
            "max_credits":payload.max_credits,"generation_started":False}

def review(request_id: UUID, payload: RefineReview, request: Request):
    user=owner(request)
    with connection() as conn:
        with conn.transaction():
            row=conn.execute("""SELECT status,expires_at FROM meshy_refine_requests
              WHERE id=%s AND created_by=%s FOR UPDATE""",(request_id,user["id"])).fetchone()
            if not row:
                raise HTTPException(404,"Refine request not found")
            if row[0]!="pending" or row[1].timestamp()<=__import__("time").time():
                raise HTTPException(409,"Already reviewed or expired")
            status="approved" if payload.decision=="approve" else "rejected"
            conn.execute("""UPDATE meshy_refine_requests SET status=%s,
              approved_at=CASE WHEN %s='approved' THEN now() ELSE NULL END WHERE id=%s""",
              (status,status,request_id))
    return {"id":str(request_id),"status":status,"generation_started":False,
            "dispatch_enabled":False}

def inspect(request_id: UUID, request: Request):
    user=owner(request)
    with connection() as conn:
        row=conn.execute("""SELECT status,dispatch_state,provider_task_id,max_credits
          FROM meshy_refine_requests WHERE id=%s AND created_by=%s""",
          (request_id,user["id"])).fetchone()
    if not row:
        raise HTTPException(404,"Refine request not found")
    return {"id":str(request_id),"status":row[0],"dispatch_state":row[1],
            "provider_task_id":row[2],"max_credits":row[3],"dispatch_enabled":False}
