"""Optional link between a Director pipeline and a Mission Control task.

The link is metadata: it never changes what a pipeline executes and is not part
of the plan digest. Pipeline milestones are appended to the task's existing
event history. A task's status stays under human control. Database problems
never affect a pipeline: every write here is best effort.
"""
from uuid import UUID
from .db import connection

EVENTS = {"started": "director.pipeline.started", "completed": "director.pipeline.completed",
          "failed": "director.pipeline.failed", "cancelled": "director.pipeline.cancelled",
          "retried": "director.pipeline.retried"}


def _uuid(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def resolve(task_id: str, owner_id: str) -> dict:
    """Validate that the task exists. Only owners launch pipelines and owners see every project."""
    task, owner = _uuid(task_id), _uuid(owner_id)
    if task is None or owner is None:
        return {"error": "invalid_task_id"}
    try:
        with connection() as conn:
            row = conn.execute("SELECT project_id,title,status FROM mission_tasks WHERE id=%s", (task,)).fetchone()
    except Exception:
        return {"error": "task_storage_unavailable"}
    if not row:
        return {"error": "task_not_found"}
    return {"task_id": str(task), "mission_project_id": str(row[0]), "title": row[1], "status": row[2]}


def record(task_id: str, owner_id: str, milestone: str) -> bool:
    task, owner = _uuid(task_id), _uuid(owner_id)
    if task is None or owner is None or milestone not in EVENTS:
        return False
    try:
        with connection() as conn:
            conn.execute("INSERT INTO mission_task_events(task_id,actor_id,event_type) VALUES (%s,%s,%s)",
                         (task, owner, EVENTS[milestone]))
            conn.execute("INSERT INTO audit_events(event_type,outcome) VALUES (%s,'success')", (EVENTS[milestone],))
        return True
    except Exception:
        return False
