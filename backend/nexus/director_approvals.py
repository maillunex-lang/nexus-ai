"""Director proposals: human approval workflow only, no execution."""
import hashlib
import json
from uuid import UUID
from fastapi import HTTPException, Request
from pydantic import BaseModel
from typing import Literal
from .db import connection
from .mission_workflow import actor, project_access

class Review(BaseModel):
    decision: Literal["approved","denied"]

def plan_for(title: str, description: str) -> dict:
    return {"goal":title,"context":description,"model":"template-v1",
      "steps":[{"name":"Анализ задачи","kind":"review"},
               {"name":"Подготовка плана","kind":"planning"},
               {"name":"Оценка рисков","kind":"security_review"},
               {"name":"Запрос разрешения на конкретные действия","kind":"approval"}],
      "execution_enabled":False}

def propose(task_id: UUID, request: Request) -> dict:
    user=actor(request,True)
    with connection() as conn:
        row=conn.execute("SELECT project_id,title,description FROM mission_tasks WHERE id=%s",(task_id,)).fetchone()
        if not row:
            raise HTTPException(404,"Task not found")
        project_access(conn,user,row[0],True)
        plan=plan_for(row[1],row[2])
        canonical=json.dumps(plan,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        digest=hashlib.sha256(canonical.encode()).hexdigest()
        created=conn.execute("""INSERT INTO director_proposals(task_id,created_by,plan,plan_digest)
           VALUES (%s,%s,%s::jsonb,%s) RETURNING id,status,expires_at""",
           (task_id,user["id"],canonical,digest)).fetchone()
        conn.execute("INSERT INTO audit_events(event_type,outcome) VALUES ('director.proposal.create','success')")
    return {"id":str(created[0]),"task_id":str(task_id),"status":created[1],
      "expires_at":created[2].isoformat(),"plan":plan,"digest":digest}

def list_proposals(project_id: UUID, request: Request) -> dict:
    user=actor(request)
    with connection() as conn:
        project_access(conn,user,project_id)
        rows=conn.execute("""SELECT d.id,d.task_id,d.status,d.plan,d.created_at,d.expires_at,d.plan_digest
          FROM director_proposals d JOIN mission_tasks t ON t.id=d.task_id
          WHERE t.project_id=%s ORDER BY d.created_at DESC LIMIT 100""",(project_id,)).fetchall()
    return {"proposals":[{"id":str(r[0]),"task_id":str(r[1]),"status":r[2],
      "plan":r[3],"created_at":r[4].isoformat(),"expires_at":r[5].isoformat(),"digest":r[6]}
      for r in rows],"execution_enabled":False}

def review_proposal(proposal_id: UUID, payload: Review, request: Request) -> dict:
    user=actor(request,True)
    if "owner" not in user["roles"]:
        raise HTTPException(403,"Owner approval required")
    with connection() as conn:
        with conn.transaction():
            row=conn.execute("""SELECT t.project_id,d.status,d.expires_at,d.created_by
              FROM director_proposals d JOIN mission_tasks t ON t.id=d.task_id
              WHERE d.id=%s FOR UPDATE OF d""",(proposal_id,)).fetchone()
            if not row:
                raise HTTPException(404,"Proposal not found")
            project_access(conn,user,row[0],True)
            if row[1]!="pending" or row[2].timestamp()<=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).timestamp():
                raise HTTPException(409,"Proposal already resolved or expired")
            if str(row[3])==str(user["id"]):
                raise HTTPException(403,"Creator cannot approve own proposal")
            conn.execute("""UPDATE director_proposals SET status=%s,reviewed_by=%s,reviewed_at=now()
              WHERE id=%s""",(payload.decision,user["id"],proposal_id))
            conn.execute("INSERT INTO audit_events(event_type,outcome) VALUES ('director.proposal.review',%s)",(payload.decision,))
    return {"id":str(proposal_id),"status":payload.decision,"execution_enabled":False,
            "note":"Approval records intent only; execution requires a separate sandboxed executor and action authorization."}
