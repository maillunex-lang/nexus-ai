"""Owner-controlled Director settings stored in the queue volume.

Which build-enabled games accept change validation is the owner's decision,
made in an authenticated dashboard session; there is deliberately no MCP tool
for it. Enabling a project only allows changes to be applied to disposable
isolated copies of it; originals stay read-only.
"""
from . import director_store as store
from .godot_job_queue import QUEUE
from .godot_projects import PROJECTS
from .mcp_principal import require_owner, require_owner_write

ROOT = QUEUE / "director-settings"
BASELINE = ("basheco",)   # always enabled: the long-standing single-file validation target


def change_enabled() -> tuple:
    data = store.read(ROOT / "change-projects.json", 4000) or {}
    chosen = data.get("projects") if isinstance(data.get("projects"), list) else []
    return tuple(sorted(set(BASELINE) | {p for p in chosen if isinstance(p, str) and p in PROJECTS}))


def describe() -> dict:
    require_owner()
    enabled = change_enabled()
    return {"change_validation": [{"project_id": key, "name": PROJECTS[key]["name"], "enabled": key in enabled,
                                   "locked": key in BASELINE} for key in sorted(PROJECTS)],
            "note": "Разрешает применять изменения только к изолированным копиям. Исходные проекты не изменяются."}


def set_change_enabled(project_id: str, enabled: bool) -> dict:
    owner = require_owner_write()
    if not isinstance(project_id, str) or project_id not in PROJECTS:
        return {"error": "project_not_build_enabled"}
    if project_id in BASELINE:
        return {"error": "baseline_project_locked"}
    if type(enabled) is not bool:
        return {"error": "invalid_value"}
    current = set(change_enabled()) - set(BASELINE)
    (current.add if enabled else current.discard)(project_id)
    store.replace(ROOT / "change-projects.json", {"projects": sorted(current), "updated_at": store.stamp(),
                                                 "updated_by": str(owner["user_id"])})
    store.append_jsonl(ROOT / "audit.jsonl", {"event": "change_validation", "project_id": project_id,
                                              "enabled": enabled, "actor": str(owner["user_id"])})
    return describe()
