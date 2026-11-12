"""Mission Control read-only API. No task execution or remote access."""
from fastapi import Request
from .db import connection
from .identity import current_user


def overview(request: Request) -> dict:
    user = current_user(request)
    if not set(user["roles"]).intersection({"owner", "operator", "viewer"}):
        from fastapi import HTTPException
        raise HTTPException(403, "Role required")
    with connection() as conn:
        if "owner" in user["roles"]:
            projects = conn.execute(
                "SELECT id, name, created_at FROM projects ORDER BY created_at DESC, id LIMIT 50"
            ).fetchall()
        else:
            projects = conn.execute(
                """SELECT p.id,p.name,p.created_at FROM projects p
                   JOIN project_memberships m ON m.project_id=p.id
                   WHERE m.user_id=%s ORDER BY p.created_at DESC LIMIT 50""",
                (user["id"],)
            ).fetchall()
        tasks = conn.execute(
            "SELECT status, count(*) FROM approval_requests GROUP BY status"
        ).fetchall()
        audit = conn.execute(
            "SELECT event_type, outcome, occurred_at FROM audit_events ORDER BY occurred_at DESC LIMIT 15"
        ).fetchall() if "owner" in user["roles"] else []
    return {
        "projects": [{"id": str(p[0]), "name": p[1], "created_at": p[2].isoformat()} for p in projects],
        "approvals": [{"status": s, "count": n} for s, n in tasks],
        "recent_events": [{"event_type": t, "outcome": o, "occurred_at": at.isoformat()} for t, o, at in audit],
        "capabilities": {"agents": False, "task_execution": False, "integrations": False},
        "read_only": True,
    }
