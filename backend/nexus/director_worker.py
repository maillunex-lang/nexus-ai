"""One-shot deterministic Director worker with leased claims and bounded recovery.

No subprocess, model API, external network, Docker or shell execution.
"""
import hashlib
import json
from datetime import datetime, timezone
from .db import connection

MAX_ATTEMPTS = 3
LEASE_SECONDS = 120


def canonical_digest(plan: dict) -> str:
    payload = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summarize(plan: dict, digest: str) -> dict:
    if canonical_digest(plan) != digest:
        raise ValueError("plan_digest_mismatch")
    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) > 50:
        raise ValueError("invalid_plan_steps")
    return {
        "type": "deterministic_plan_review",
        "model_used": False,
        "execution_enabled": False,
        "plan_digest": digest,
        "goal": str(plan.get("goal", ""))[:200],
        "step_count": len(steps),
        "recommendation": "Проверить критерии готовности, риски и разрешения перед выполнением",
    }


def recover_expired() -> dict:
    """Recover only abandoned leases; never retry more than MAX_ATTEMPTS."""
    with connection() as conn:
        with conn.transaction():
            failed = conn.execute("""
                UPDATE director_jobs SET status='failed',lease_until=NULL,
                  error_code='lease_expired_max_attempts',updated_at=now()
                WHERE status='running' AND lease_until < now() AND attempts >= %s
                RETURNING id
            """, (MAX_ATTEMPTS,)).fetchall()
            retried = conn.execute("""
                UPDATE director_jobs SET status='queued',lease_until=NULL,
                  error_code='lease_expired_retry',updated_at=now()
                WHERE status='running' AND lease_until < now() AND attempts < %s
                RETURNING id
            """, (MAX_ATTEMPTS,)).fetchall()
            for (job_id,) in failed:
                conn.execute("INSERT INTO director_job_events(job_id,event) VALUES (%s,'failed_lease')", (job_id,))
            for (job_id,) in retried:
                conn.execute("INSERT INTO director_job_events(job_id,event) VALUES (%s,'retry_lease')", (job_id,))
    return {"failed": len(failed), "retried": len(retried)}


def process_one() -> dict:
    with connection() as conn:
        with conn.transaction():
            row = conn.execute("""
                SELECT j.id,d.plan,d.plan_digest FROM director_jobs j
                JOIN director_proposals d ON d.id=j.proposal_id
                WHERE j.status='queued' AND j.attempts < %s
                  AND d.status='approved' AND d.expires_at>now()
                ORDER BY j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 1
            """, (MAX_ATTEMPTS,)).fetchone()
            if not row:
                return {"processed": False}
            job_id, plan, digest = row
            claimed = conn.execute("""
                UPDATE director_jobs SET status='running',attempts=attempts+1,
                  lease_until=now()+(%s * interval '1 second'),updated_at=now()
                WHERE id=%s AND status='queued' RETURNING id
            """, (LEASE_SECONDS, job_id)).fetchone()
            if not claimed:
                return {"processed": False, "reason": "claim_lost"}
            conn.execute("INSERT INTO director_job_events(job_id,event) VALUES (%s,'started')", (job_id,))

    try:
        result = summarize(plan, digest)
    except (ValueError, TypeError, AttributeError) as exc:
        error_code = str(exc) if str(exc) in {"plan_digest_mismatch", "invalid_plan_steps"} else "invalid_plan"
        with connection() as conn:
            with conn.transaction():
                changed = conn.execute("""
                    UPDATE director_jobs SET status='failed',error_code=%s,
                      lease_until=NULL,updated_at=now()
                    WHERE id=%s AND status='running' AND lease_until>now() RETURNING id
                """, (error_code, job_id)).fetchone()
                if changed:
                    conn.execute("INSERT INTO director_job_events(job_id,event) VALUES (%s,'failed_validation')", (job_id,))
        return {"processed": False, "job_id": str(job_id), "reason": error_code}

    with connection() as conn:
        with conn.transaction():
            updated = conn.execute("""
                UPDATE director_jobs SET status='succeeded',result=%s::jsonb,
                  error_code=NULL,lease_until=NULL,updated_at=now()
                WHERE id=%s AND status='running' AND lease_until>now() RETURNING id
            """, (json.dumps(result, ensure_ascii=False), job_id)).fetchone()
            if not updated:
                return {"processed": False, "reason": "lease_lost"}
            conn.execute("INSERT INTO director_job_events(job_id,event) VALUES (%s,'succeeded')", (job_id,))
    return {"processed": True, "job_id": str(job_id), "result": result}


if __name__ == "__main__":
    print(json.dumps({"recovery": recover_expired(), "run": process_one()}, ensure_ascii=False))
