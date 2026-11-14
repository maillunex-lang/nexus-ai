"""Typed NEXUS↔Termalin connector contract.

The backend validates and records intents. Actual host execution remains delegated
to the connected Termalin layer. No SSH keys, arbitrary shell or provider secrets
are stored here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class Operation(str, Enum):
    compose_up = "compose_up"
    compose_restart = "compose_restart"
    compose_down = "compose_down"
    sftp_write = "sftp_write"
    job_start = "job_start"
    db_migrate = "db_migrate"
    rollback = "rollback"


class Inventory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host_id: str = Field(min_length=1, max_length=120)
    host_name: str = Field(min_length=1, max_length=120)
    projects: list[str] = Field(default_factory=list, max_length=100)
    ports: list[int] = Field(default_factory=list, max_length=500)
    containers: list[str] = Field(default_factory=list, max_length=300)
    metrics: dict[str, float | int | bool | str | None] = Field(default_factory=dict)
    observed_at: str = Field(default="", max_length=80)

    @field_validator("host_id", "host_name", "observed_at")
    @classmethod
    def safe_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("NUL is not allowed")
        return value.strip()

    @field_validator("projects", "containers")
    @classmethod
    def safe_items(cls, values: list[str]) -> list[str]:
        if any(not isinstance(v, str) or not v.strip() or "\x00" in v for v in values):
            raise ValueError("invalid inventory item")
        return sorted(set(v.strip() for v in values))


class OperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host_id: str = Field(min_length=1, max_length=120)
    project: str = Field(min_length=1, max_length=120)
    operation: Operation
    compose_file: str | None = Field(default=None, max_length=300)
    target_path: str | None = Field(default=None, max_length=500)
    backup_ref: str | None = Field(default=None, max_length=300)
    rollback_ref: str | None = Field(default=None, max_length=300)
    approval_id: str | None = Field(default=None, max_length=200)
    timeout_seconds: int = Field(default=60, ge=1, le=300)

    @field_validator("host_id", "project", "compose_file", "target_path", "backup_ref", "rollback_ref", "approval_id")
    @classmethod
    def safe_text(cls, value):
        if value is not None and ("\x00" in value or "\n" in value or "\r" in value):
            raise ValueError("unsafe text")
        return value.strip() if isinstance(value, str) else value


WRITE_OPERATIONS = {
    Operation.compose_up, Operation.compose_restart, Operation.compose_down,
    Operation.sftp_write, Operation.job_start, Operation.db_migrate,
    Operation.rollback,
}
PROTECTED_PROJECTS = {"cosmocrpg", "basheco", "watermmo", "pocketbase", "agroapp"}
PROJECT_ROOTS = {
    "nexus-ai": "/opt/nexus-ai",
    "nexus-ai-dev": "/opt/nexus-ai",
    "lunex-music-studio": "/opt/lunex-music-studio",
}


def catalog() -> dict:
    return {
        "version": 1,
        "mode": "typed_intent_delegation",
        "execution": "delegated_to_terminall",
        "operations": [operation.value for operation in Operation],
        "write_operations": sorted(operation.value for operation in WRITE_OPERATIONS),
        "protected_projects": sorted(PROTECTED_PROJECTS),
        "project_roots": dict(PROJECT_ROOTS),
        "limits": [
            "No SSH keys or provider secrets are stored.",
            "No arbitrary shell commands are accepted.",
            "Writes require owner OAuth, approval_id, backup_ref and rollback_ref.",
            "Termalin performs the actual host operation and returns execution evidence.",
        ],
    }


def normalize_inventory(snapshot: dict) -> dict:
    try:
        inventory = Inventory.model_validate(snapshot)
    except ValidationError:
        return {"error": "invalid_inventory"}
    if not inventory.observed_at:
        inventory.observed_at = datetime.now(timezone.utc).isoformat()
    # Never carry secret-looking keys through the bridge.
    safe_metrics = {
        key: value for key, value in inventory.metrics.items()
        if not any(token in key.lower() for token in ("secret", "token", "password", "private_key", "credential"))
    }
    inventory.metrics = safe_metrics
    return {"inventory": inventory.model_dump(), "read_only": True, "secrets_redacted": True}


def plan(request_data: dict, snapshot: dict) -> dict:
    try:
        request = OperationRequest.model_validate(request_data)
        inventory = Inventory.model_validate(snapshot)
    except ValidationError:
        return {"error": "invalid_request_or_inventory"}
    if request.host_id != inventory.host_id:
        return {"error": "host_mismatch"}
    if request.project in PROTECTED_PROJECTS:
        return {"error": "protected_project_requires_separate_authorization"}
    if request.project not in PROJECT_ROOTS:
        return {"error": "project_not_allowlisted"}
    if request.project not in inventory.projects and request.project != "nexus-ai":
        return {"error": "project_not_present_in_inventory"}
    if request.operation in WRITE_OPERATIONS:
        missing = [
            name for name, value in (
                ("approval_id", request.approval_id),
                ("backup_ref", request.backup_ref),
                ("rollback_ref", request.rollback_ref),
            ) if not value
        ]
        if missing:
            return {"error": "write_gate_missing", "missing": missing}
    if request.operation in {Operation.compose_up, Operation.compose_restart, Operation.compose_down, Operation.db_migrate} and not request.compose_file:
        return {"error": "compose_file_required"}
    if request.operation == Operation.sftp_write and not request.target_path:
        return {"error": "target_path_required"}
    return {
        "plan": {
            "host_id": request.host_id,
            "project": request.project,
            "operation": request.operation.value,
            "target_root": PROJECT_ROOTS[request.project],
            "compose_file": request.compose_file,
            "target_path": request.target_path,
            "backup_ref": request.backup_ref,
            "rollback_ref": request.rollback_ref,
            "timeout_seconds": request.timeout_seconds,
        },
        "execution": "delegated_to_terminall",
        "requires_owner_write": request.operation in WRITE_OPERATIONS,
        "original_source_modified": False,
        "next_step": "Execute the exact approved plan through Termalin and return evidence.",
    }


def verify(expected: dict, observed: dict) -> dict:
    if not isinstance(expected, dict) or not isinstance(observed, dict):
        return {"error": "invalid_verification_payload"}
    expected_containers = set(expected.get("containers", []))
    observed_containers = set(observed.get("containers", []))
    expected_ports = set(expected.get("ports", []))
    observed_ports = set(observed.get("ports", []))
    missing_containers = sorted(expected_containers - observed_containers)
    missing_ports = sorted(expected_ports - observed_ports)
    health = observed.get("health", "unknown")
    passed = not missing_containers and not missing_ports and health in {"ok", "healthy"}
    return {
        "passed": passed,
        "health": health,
        "missing_containers": missing_containers,
        "missing_ports": missing_ports,
        "evidence": observed.get("evidence", []),
        "rollback_recommended": not passed,
    }
