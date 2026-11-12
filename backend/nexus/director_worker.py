"""Opt-in one-shot Director planning worker. No external commands, network or model calls."""
import json
from .db import connection

def process_one() -> dict:
    with connection() as conn:
        with conn.transaction():
            row=conn.execute("""SELECT j.id,d.plan,d.plan_digest FROM director_jobs j
              JOIN director_proposals d ON d.id=j.proposal_id
              WHERE j.status='queued' AND d.status='approved' AND d.expires_at>now()
              ORDER BY j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 1""").fetchone()
            if not row:
                return {"processed":False}
            job_id,plan,digest=row
            conn.execute("""UPDATE director_jobs SET status='running',attempts=attempts+1,
              lease_until=now()+interval '2 minutes',updated_at=now() WHERE id=%s""",(job_id,))
            conn.execute("INSERT INTO director_job_events(job_id,event) VALUES (%s,'started')",(job_id,))
    result={"type":"deterministic_plan_review","model_used":False,"execution_enabled":False,
            "plan_digest":digest,"goal":plan.get("goal",""),"step_count":len(plan.get("steps",[])),
            "recommendation":"Проверить критерии готовности, риски и разрешения перед выполнением"}
    with connection() as conn:
        with conn.transaction():
            updated=conn.execute("""UPDATE director_jobs SET status='succeeded',result=%s::jsonb,
              lease_until=NULL,updated_at=now()
              WHERE id=%s AND status='running' AND lease_until>now() RETURNING id""",
              (json.dumps(result,ensure_ascii=False),job_id)).fetchone()
            if not updated:
                return {"processed":False,"reason":"lease_lost"}
            conn.execute("INSERT INTO director_job_events(job_id,event) VALUES (%s,'succeeded')",(job_id,))
    return {"processed":True,"job_id":str(job_id),"result":result}

if __name__=="__main__":
    print(json.dumps(process_one(),ensure_ascii=False))
