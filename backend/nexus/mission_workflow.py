"""Mission Control CRUD and safe Director planning. Never executes user commands."""
from uuid import UUID
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from typing import Literal
from .db import connection
from .identity import current_user

Status = Literal["backlog","ready","in_progress","blocked","done","cancelled"]
Agent = Literal["director","developer","tester","devops","artist"]

class ProjectCreate(BaseModel):
    name: str = Field(min_length=3,max_length=160)

class TaskCreate(BaseModel):
    project_id: UUID
    title: str = Field(min_length=3,max_length=200)
    description: str = Field(default="",max_length=10000)

class TaskUpdate(BaseModel):
    status: Status
    assigned_agent: Agent | None = None
    version: int = Field(ge=1)

def actor(request: Request, write: bool=False) -> dict:
    user = current_user(request)
    roles = set(user["roles"])
    if not roles.intersection({"owner","operator","viewer"}):
        raise HTTPException(403,"Role required")
    if write and not roles.intersection({"owner","operator"}):
        raise HTTPException(403,"Write permission required")
    return user

def project_access(conn, user: dict, project_id: UUID, write: bool=False) -> None:
    if "owner" in user["roles"]:
        exists=conn.execute("SELECT 1 FROM projects WHERE id=%s",(project_id,)).fetchone()
    else:
        roles=("owner","operator") if write else ("owner","operator","viewer")
        exists=conn.execute("""SELECT 1 FROM projects p JOIN project_memberships m ON m.project_id=p.id
          WHERE p.id=%s AND m.user_id=%s AND m.role_id=ANY(%s)""",(project_id,user["id"],list(roles))).fetchone()
    if not exists:
        raise HTTPException(404,"Project not found")

def create_project(payload: ProjectCreate, request: Request) -> dict:
    user=actor(request,True)
    name=payload.name.strip()
    if len(name)<3:
        raise HTTPException(422,"Project name too short")
    with connection() as conn:
        row=conn.execute("INSERT INTO projects(name) VALUES (%s) RETURNING id,name,created_at",(name,)).fetchone()
        conn.execute("INSERT INTO project_memberships(project_id,user_id,role_id) VALUES (%s,%s,%s)",(row[0],user["id"],"owner" if "owner" in user["roles"] else "operator"))
        conn.execute("INSERT INTO audit_events(event_type,outcome) VALUES ('mission.project.create','success')")
    return {"id":str(row[0]),"name":row[1],"created_at":row[2].isoformat()}

def list_projects(request: Request) -> dict:
    user=actor(request)
    with connection() as conn:
        if "owner" in user["roles"]:
            rows=conn.execute("SELECT id,name,created_at FROM projects ORDER BY created_at DESC LIMIT 100").fetchall()
        else:
            rows=conn.execute("""SELECT p.id,p.name,p.created_at FROM projects p
              JOIN project_memberships m ON m.project_id=p.id
              WHERE m.user_id=%s ORDER BY p.created_at DESC LIMIT 100""",(user["id"],)).fetchall()
    return {"projects":[{"id":str(r[0]),"name":r[1],"created_at":r[2].isoformat()} for r in rows]}

def create_task(payload: TaskCreate, request: Request) -> dict:
    user=actor(request,True)
    title=payload.title.strip()
    if len(title)<3:
        raise HTTPException(422,"Title too short")
    with connection() as conn:
        project_access(conn,user,payload.project_id,True)
        row=conn.execute("""INSERT INTO mission_tasks(project_id,title,description,created_by,updated_by)
          VALUES (%s,%s,%s,%s,%s) RETURNING id,status,version""",
          (payload.project_id,title,payload.description,user["id"],user["id"])).fetchone()
        conn.execute("""INSERT INTO mission_task_events(task_id,actor_id,event_type,new_status)
          VALUES (%s,%s,'created',%s)""",(row[0],user["id"],row[1]))
        conn.execute("INSERT INTO audit_events(event_type,outcome) VALUES ('mission.task.create','success')")
    return {"id":str(row[0]),"project_id":str(payload.project_id),"title":title,"status":row[1],"version":row[2]}

def list_tasks(project_id: UUID, request: Request) -> dict:
    user=actor(request)
    with connection() as conn:
        project_access(conn,user,project_id)
        rows=conn.execute("""SELECT id,title,description,status,assigned_agent,version,created_at
          FROM mission_tasks WHERE project_id=%s ORDER BY created_at DESC LIMIT 200""",(project_id,)).fetchall()
    return {"tasks":[{"id":str(r[0]),"title":r[1],"description":r[2],"status":r[3],
       "assigned_agent":r[4],"version":r[5],"created_at":r[6].isoformat()} for r in rows]}

TRANSITIONS={
 "backlog":{"ready","cancelled"}, "ready":{"in_progress","blocked","cancelled"},
 "in_progress":{"blocked","done","cancelled"}, "blocked":{"ready","cancelled"},
 "done":set(), "cancelled":set()
}

def update_task(task_id: UUID, payload: TaskUpdate, request: Request) -> dict:
    user=actor(request,True)
    with connection() as conn:
        with conn.transaction():
            row=conn.execute("SELECT project_id,status,version FROM mission_tasks WHERE id=%s FOR UPDATE",(task_id,)).fetchone()
            if not row:
                raise HTTPException(404,"Task not found")
            project_access(conn,user,row[0],True)
            if row[2]!=payload.version:
                raise HTTPException(409,"Task version changed")
            if payload.status!=row[1] and payload.status not in TRANSITIONS[row[1]]:
                raise HTTPException(409,"Invalid task status transition")
            conn.execute("""UPDATE mission_tasks SET status=%s,assigned_agent=%s,version=version+1,
              updated_at=now(),updated_by=%s WHERE id=%s""",
              (payload.status,payload.assigned_agent,user["id"],task_id))
            conn.execute("""INSERT INTO mission_task_events(task_id,actor_id,event_type,old_status,new_status)
              VALUES (%s,%s,'updated',%s,%s)""",(task_id,user["id"],row[1],payload.status))
            conn.execute("INSERT INTO audit_events(event_type,outcome) VALUES ('mission.task.update','success')")
    return {"id":str(task_id),"status":payload.status,"assigned_agent":payload.assigned_agent,
            "version":payload.version+1,"execution_enabled":False}

def director_plan(task_id: UUID, request: Request) -> dict:
    """Deterministic draft, not LLM execution or access to VPS tools."""
    user=actor(request)
    with connection() as conn:
        row=conn.execute("SELECT project_id,title,status,assigned_agent FROM mission_tasks WHERE id=%s",(task_id,)).fetchone()
        if not row:
            raise HTTPException(404,"Task not found")
        project_access(conn,user,row[0])
    return {"task_id":str(task_id),"mode":"proposal_only","execution_enabled":False,
            "agent":row[3] or "director",
            "steps":["Уточнить критерии готовности","Подготовить план реализации",
                     "Проверить риски и необходимые разрешения","После отдельного разрешения выполнить работу",
                     "Провести тесты и подготовить отчёт"],
            "note":"План шаблонный. AI-модель и исполнитель команд не подключены."}
