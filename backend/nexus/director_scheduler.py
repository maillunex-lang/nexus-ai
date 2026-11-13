"""Optional in-process schedule for Director transitions and retention.

Disabled unless NEXUS_DIRECTOR_TICK_SECONDS is set (15-3600). When enabled, the
API process advances already-authorized pipelines on that interval, so no one
has to poll, and runs retention at most once an hour. It needs no host timer,
shell or extra container. With several API processes the per-pipeline lock
keeps every transition single.
"""
import asyncio
import os
import time
from .director_pipelines import tick
from .director_retention import purge

RETENTION_INTERVAL = 3600
_last_retention = 0.0


def interval() -> int:
    raw = os.environ.get("NEXUS_DIRECTOR_TICK_SECONDS", "")
    try:
        seconds = int(raw)
    except ValueError:
        return 0
    return seconds if 15 <= seconds <= 3600 else 0


def run_once(now: float | None = None) -> dict:
    """One scheduled pass. Never raises: a failing pass must not stop the schedule."""
    global _last_retention
    now = time.time() if now is None else now
    result = {}
    try:
        result["tick"] = tick()
    except Exception as exc:
        result["tick_error"] = type(exc).__name__
    if now - _last_retention >= RETENTION_INTERVAL:
        _last_retention = now
        try:
            result["retention"] = purge(now=now)
        except Exception as exc:
            result["retention_error"] = type(exc).__name__
    return result


async def loop(seconds: int) -> None:
    while True:
        await asyncio.sleep(seconds)
        await asyncio.to_thread(run_once)


def start():
    """Create the background task when scheduling is enabled; otherwise None."""
    seconds = interval()
    return asyncio.create_task(loop(seconds)) if seconds else None
