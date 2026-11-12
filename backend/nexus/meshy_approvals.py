"""Owner-only Meshy request approvals. Explicitly no Meshy POST/execution."""
from uuid import UUID
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from typing import Literal
from .db import connection
from .identity import current_user
from .meshy_proposals import preview_text_to_3d

class MeshyRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=600)
    art_style: Literal["realistic", "sculpture"] = "realistic"
    mode: Literal["preview", "refine"] = "preview"
    max_credits: int = Field(ge=1, le=1000)

class MeshyReview(BaseModel):
    decision: Literal["approve", "reject"]

def owner(request: Request):
    user = current_user(request)
    if "owner" not in user["roles"]:
        raise HTTPException(403, "Owner role required")
    return user

def create(payload: MeshyRequest, request: Request):
    user = owner(request)
    preview = preview_text_to_3d(payload.prompt, payload.art_style, payload.mode)
    if "error" in preview:
        raise HTTPException(422, preview["error"])
    from psycopg.types.json import Jsonb
    with connection() as conn:
        row = conn.execute("""INSERT INTO meshy_requests(created_by,proposal_sha256,proposal,max_credits)
          VALUES (%s,%s,%s,%s) RETURNING id,expires_at""",
          (user["id"],preview["proposal_sha256"],Jsonb(preview["proposal"]),payload.max_credits)).fetchone()
        conn.execute("INSERT INTO meshy_request_events(request_id,actor_id,action) VALUES (%s,%s,'created')",
                     (row[0],user["id"]))
    return {"id":str(row[0]),"status":"pending","proposal_sha256":preview["proposal_sha256"],
            "max_credits":payload.max_credits,"expires_at":row[1].isoformat(),
            "cost_verified":False,"generation_started":False}

def review(request_id: UUID, payload: MeshyReview, request: Request):
    user = owner(request)
    with connection() as conn:
        with conn.transaction():
            row=conn.execute("""SELECT created_by,status,expires_at FROM meshy_requests
              WHERE id=%s FOR UPDATE""",(request_id,)).fetchone()
            if not row or row[0]!=user["id"]:
                raise HTTPException(404,"Request not found")
            if row[1]!="pending" or row[2].timestamp() <= __import__("time").time():
                raise HTTPException(409,"Request already resolved or expired")
            status="approved" if payload.decision=="approve" else "rejected"
            conn.execute("""UPDATE meshy_requests SET status=%s,approved_by=%s,
              approved_at=CASE WHEN %s='approved' THEN now() ELSE NULL END WHERE id=%s""",
              (status,user["id"] if status=="approved" else None,status,request_id))
            conn.execute("""INSERT INTO meshy_request_events(request_id,actor_id,action)
              VALUES (%s,%s,%s)""",(request_id,user["id"],status))
    return {"id":str(request_id),"status":status,"generation_started":False,
            "cost_verified":False,"execution_enabled":False}

def list_requests(request: Request):
    user=owner(request)
    with connection() as conn:
        rows=conn.execute("""SELECT id,status,max_credits,created_at,expires_at
          FROM meshy_requests WHERE created_by=%s ORDER BY created_at DESC LIMIT 50""",
          (user["id"],)).fetchall()
    return {"requests":[{"id":str(r[0]),"status":r[1],"max_credits":r[2],
             "created_at":r[3].isoformat(),"expires_at":r[4].isoformat()} for r in rows],
            "generation_enabled":False}
