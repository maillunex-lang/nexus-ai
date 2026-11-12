"""Durable, human-approved planning jobs. No shell, subprocess or network tools."""
from uuid import UUID
from fastapi import HTTPException, Request
from .db import connection
from .mission_workflow import actor, project_access

def enqueue(proposal_id: UUID, request: Request) -> dict:
    user=actor(request,True)
    if "owner" not in user["roles"]:
        raise HTTPException(403,"Owner required")
    with connection() as conn:
        with conn.transaction():
            row=conn.execute("""SELECT t.project_id,d.status,d.expires_at,d.reviewed_by,d.created_by
              FROM director_proposals d JOIN mission_tasks t ON t.id=d.task_id
              WHERE d.id=%s FOR UPDATE OF d""",(proposal_id,)).fetchone()
            if not row:
                raise HTTPException(404,"Proposal not found")
            project_access(conn,user,row[0],True)
            if row[1]!="approved" or row[2]<=__import__("datetime").datetime.now(__import__("datetime").timezone.utc):
                raise HTTPException(409,"Approved unexpired proposal required")
            if str(row[3])==str(row[4]):
                raise HTTPException(409,"Independent review required")
            existing=conn.execute("SELECT id,status FROM director_jobs WHERE proposal_id=%s",(proposal_id,)).fetchone()
            if existing:
                return {"id":str(existing[0]),"status":existing[1],"execution_enabled":False,"already_exists":True}
            job=conn.execute("""INSERT INTO director_jobs(proposal_id,requested_by)
              VALUES (%s,%s) RETURNING id,status""",(proposal_id,user["id"])).fetchone()
            conn.execute("INSERT INTO director_job_events(job_id,event) VALUES (%s,'queued')",(job[0],))
            conn.execute("INSERT INTO audit_events(event_type,outcome) VALUES ('director.job.enqueue','success')")
    return {"id":str(job[0]),"status":job[1],"execution_enabled":False,"already_exists":False}

def list_jobs(project_id: UUID, request: Request) -> dict:
    user=actor(request)
    with connection() as conn:
        project_access(conn,user,project_id)
        rows=conn.execute("""SELECT j.id,j.proposal_id,j.status,j.attempts,j.created_at,j.updated_at,j.result,j.error_code
          FROM director_jobs j JOIN director_proposals d ON d.id=j.proposal_id
          JOIN mission_tasks t ON t.id=d.task_id
          WHERE t.project_id=%s ORDER BY j.created_at DESC LIMIT 100""",(project_id,)).fetchall()
    return {"jobs":[{"id":str(r[0]),"proposal_id":str(r[1]),"status":r[2],"attempts":r[3],
      "created_at":r[4].isoformat(),"updated_at":r[5].isoformat(),"result":r[6],"error_code":r[7]}
      for r in rows],"execution_enabled":False}

def cancel(job_id: UUID, request: Request) -> dict:
    user=actor(request,True)
    if "owner" not in user["roles"]:
        raise HTTPException(403,"Owner required")
    with connection() as conn:
        with conn.transaction():
            row=conn.execute("""SELECT t.project_id,j.status FROM director_jobs j
              JOIN director_proposals d ON d.id=j.proposal_id
              JOIN mission_tasks t ON t.id=d.task_id WHERE j.id=%s FOR UPDATE OF j""",(job_id,)).fetchone()
            if not row:
                raise HTTPException(404,"Job not found")
            project_access(conn,user,row[0],True)
            if row[1]!="queued":
                raise HTTPException(409,"Only queued jobs can be cancelled")
            conn.execute("UPDATE director_jobs SET status='cancelled',updated_at=now() WHERE id=%s",(job_id,))
            conn.execute("INSERT INTO director_job_events(job_id,event) VALUES (%s,'cancelled')",(job_id,))
    return {"id":str(job_id),"status":"cancelled","execution_enabled":False}
