"""Owner-scoped durable Director error journal with deterministic classification.

Every failed pipeline stage is recorded once with a category, a handling policy
and a concrete next action. Nothing here retries, edits code or calls a model:
the journal explains failures so the owner (or the connected chat) can decide.
"""
import hashlib
import os
import re
from pathlib import Path
from . import director_store as store
from .godot_job_queue import QUEUE
from .mcp_principal import require_owner

ROOT = QUEUE / "director-errors"
MAX_JOURNAL_BYTES = 1_000_000
MAX_DETAIL = 2000
MAX_DIAGNOSTICS = 20

# Ordered: first matching needle wins. `retryable` only permits an explicit,
# owner-requested retry; nothing is ever retried automatically.
CATEGORIES = (
    ("verification_blocked", ("verification_blocked",), "reject_without_retry", False,
     "Исправьте замечания проверки и создайте новый набор изменений."),
    ("source_changed", ("source_changed",), "reject_without_retry", False,
     "Исходный файл изменился. Прочитайте актуальный SHA-256 и создайте новый набор изменений."),
    ("changeset_invalid", ("changeset_", "plan_digest_mismatch"), "reject_without_retry", False,
     "Набор изменений недоступен или изменён. Создайте новый."),
    ("project_not_build_enabled", ("project_not_build_enabled", "unknown_or_unconfigured_project", "project_not_allowlisted", "change_validation_not_enabled"),
     "reject_without_retry", False, "Для проекта не разрешена эта операция. Требуется отдельное решение владельца."),
    ("project_unavailable", ("project_unavailable", "unknown_project", "not_a_godot_project"), "stop_and_report", True,
     "Каталог проекта недоступен API. Проверьте подключение проекта на сервере."),
    ("android_preset_unavailable", ("android_preset_unavailable",), "stop_and_report", False,
     "В проекте нет пресета экспорта Android (export_presets.cfg). Добавьте его в исходный проект."),
    ("toolchain_unavailable", ("export_templates_unavailable", "approved_godot_binary_unavailable", "sandbox_unavailable",
                               "java_keytool_unavailable", "godot_or_bubblewrap_unavailable"), "stop_and_report", True,
     "На сервере сборки отсутствует инструмент. Требуется администратор сервера."),
    ("worker_timeout", ("worker_timeout", "timed_out", "TimeoutExpired"), "stop_and_report", True,
     "Задание не было обработано вовремя. Проверьте, что хост-воркер запущен, затем повторите."),
    ("godot_validation_failed", ("godot_validation_failed", "Parse Error", "SCRIPT ERROR"), "stop_and_report", False,
     "Godot отклонил проект. Изучите диагностику, исправьте код и создайте новый набор изменений."),
    ("invalid_request", ("invalid_", "unsupported_", "no_changes", "validated_owned_job_required"), "reject_without_retry", False,
     "Запрос некорректен. Проверьте параметры."),
    ("job_unavailable", ("underlying_job_unavailable", "not_found"), "stop_and_report", True,
     "Результат задания недоступен. Повторите этап."),
    ("build_failed", ("build_failed", "artifact_already_exists"), "stop_and_report", True,
     "Сборка APK завершилась ошибкой. Изучите журнал сборки."),
)
DEFAULT = ("unknown", "stop_and_report", True, "Неизвестная ошибка. Изучите подробности в журнале.")


def classify(error: str) -> dict:
    text = str(error or "")
    for category, needles, policy, retryable, action in CATEGORIES:
        if any(needle in text for needle in needles):
            return {"category": category, "policy": policy, "retryable": retryable,
                    "auto_retry": False, "next_action": action}
    return {"category": DEFAULT[0], "policy": DEFAULT[1], "retryable": DEFAULT[2],
            "auto_retry": False, "next_action": DEFAULT[3]}


def diagnostics(output: str) -> list[dict]:
    """Extract structured Godot errors (kind, message, res:// file, line) from a log."""
    found = []
    lines = str(output or "")[-20000:].splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"\s*(SCRIPT ERROR|USER SCRIPT ERROR|USER ERROR|ERROR|Parse Error):\s*(.*)", line)
        if not match:
            continue
        kind = "script_error" if "SCRIPT" in match.group(1) or match.group(1) == "Parse Error" or "Parse Error" in match.group(2) else "engine_error"
        entry = {"kind": kind, "message": match.group(2).strip()[:300]}
        location = re.search(r"res://([^\s:()\"']{1,240}):(\d{1,7})", line)
        if not location and index + 1 < len(lines) and re.match(r"\s*at:", lines[index + 1]):
            location = re.search(r"res://([^\s:()\"']{1,240}):(\d{1,7})", lines[index + 1])
        if location:
            entry["file"] = location.group(1)
            entry["line"] = int(location.group(2))
        else:
            mentioned = re.search(r"res://([^\s:()\"']{1,240})", line)
            if mentioned:
                entry["file"] = mentioned.group(1)
        if entry not in found:
            found.append(entry)
        if len(found) >= MAX_DIAGNOSTICS:
            break
    return found


def _journal(owner_id: str) -> Path:
    # Owner identifiers are hashed: never used as a path component directly.
    return ROOT / (hashlib.sha256(str(owner_id).encode("utf-8")).hexdigest()[:32] + ".jsonl")


def record(owner_id: str, *, source: str, project_id: str, stage: str, error: str,
           detail: str = "", reference: str = "", agent: str = "") -> dict:
    """Append one classified error for an owner. Called by Director internals only."""
    classification = classify(error)
    entry = {"error_id": "err-" + hashlib.sha256(f"{reference}:{stage}:{error}:{store.stamp()}".encode()).hexdigest()[:16],
             "source": source[:60], "reference": reference[:60], "project_id": str(project_id)[:40],
             "stage": stage[:60], "agent": agent[:20], "error": str(error)[:300],
             **classification, "diagnostics": diagnostics(detail),
             "detail": str(detail or "")[-MAX_DETAIL:]}
    path = _journal(owner_id)
    try:
        if path.is_file() and not path.is_symlink() and path.stat().st_size > MAX_JOURNAL_BYTES:
            os.replace(path, path.with_suffix(".jsonl.1"))
        store.append_jsonl(path, entry)
    except (OSError, ValueError):
        entry["journal_write_failed"] = True
    return entry


def list_errors(limit: int = 20, project_id: str = "") -> dict:
    owner = require_owner()
    if type(limit) is not int or not 1 <= limit <= 100:
        return {"error": "invalid_limit"}
    if not isinstance(project_id, str) or len(project_id) > 40:
        return {"error": "invalid_project_id"}
    events = store.read_jsonl(_journal(owner["user_id"]), 500)
    if project_id:
        events = [e for e in events if e.get("project_id") == project_id]
    categories = {}
    for event in events:
        categories[event.get("category", "unknown")] = categories.get(event.get("category", "unknown"), 0) + 1
    return {"errors": list(reversed(events[-limit:])), "total_recent": len(events),
            "by_category": categories, "auto_retry": False, "read_only": True}
