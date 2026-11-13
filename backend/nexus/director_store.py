"""Bounded, symlink-safe JSON record storage for Director state.

Records live in the shared Godot queue volume, the only location the API
container may write. Every write is owner-only (0600), never follows symlinks,
and replacement is atomic. No path component is ever taken from user input:
callers pass identifiers that already matched a strict pattern.
"""
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

LOCK_STALE_SECONDS = 120


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_new(path: Path, data: dict) -> None:
    """Create a record that must not already exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def replace(path: Path, data: dict) -> None:
    """Atomically replace an existing record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / ("." + path.stem + "-" + uuid.uuid4().hex + ".tmp")
    fd = os.open(str(temporary), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def read(path: Path, max_bytes: int) -> dict | None:
    """Read a bounded regular-file JSON object; None when absent or invalid."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def append_jsonl(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("invalid_journal")
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"time": stamp(), **event}, ensure_ascii=False) + "\n")


def read_jsonl(path: Path, limit: int, max_bytes: int = 2_000_000) -> list[dict]:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
            return []
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    events = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


@contextmanager
def lock(path: Path):
    """Exclusive advisory lock file. Yields False when another holder is active.

    A lock older than LOCK_STALE_SECONDS belongs to a crashed process and is
    reclaimed once, so a pipeline can never be blocked forever.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    acquired = False
    for _ in range(2):
        try:
            os.close(os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600))
            acquired = True
            break
        except FileExistsError:
            try:
                if path.is_symlink() or time.time() - path.lstat().st_mtime <= LOCK_STALE_SECONDS:
                    break
                path.unlink(missing_ok=True)
            except OSError:
                break
    try:
        yield acquired
    finally:
        if acquired:
            path.unlink(missing_ok=True)
