from nexus.infrastructure_bridge import catalog, normalize_inventory, plan, verify


def inventory():
    return {
        "host_id": "lunex-1",
        "host_name": "Lunex",
        "projects": ["nexus-ai", "lunex-music-studio"],
        "ports": [22, 80, 443, 4189],
        "containers": ["nexus-ai-dev-api-1"],
        "metrics": {"cpu": 2.0, "secret_token": "redact"},
    }


def test_inventory_redacts_and_normalizes():
    result = normalize_inventory(inventory())
    assert result["read_only"] is True
    assert result["secrets_redacted"] is True
    assert "secret_token" not in result["inventory"]["metrics"]


def test_write_plan_requires_all_gates():
    result = plan({
        "host_id": "lunex-1", "project": "nexus-ai",
        "operation": "compose_restart", "compose_file": "compose.yaml",
    }, inventory())
    assert result["error"] == "write_gate_missing"
    assert set(result["missing"]) == {"approval_id", "backup_ref", "rollback_ref"}


def test_plan_accepts_exact_scoped_intent():
    result = plan({
        "host_id": "lunex-1", "project": "nexus-ai",
        "operation": "compose_restart", "compose_file": "compose.yaml",
        "approval_id": "approval-1", "backup_ref": "backup-1", "rollback_ref": "rollback-1",
    }, inventory())
    assert result["execution"] == "delegated_to_terminall"
    assert result["plan"]["target_root"] == "/opt/nexus-ai"


def test_protected_project_is_rejected():
    result = plan({
        "host_id": "lunex-1", "project": "cosmocrpg",
        "operation": "compose_restart", "compose_file": "compose.yml",
        "approval_id": "a", "backup_ref": "b", "rollback_ref": "r",
    }, inventory())
    assert result["error"] == "protected_project_requires_separate_authorization"


def test_verify_recommends_rollback():
    result = verify(
        {"containers": ["api", "db"], "ports": [4189]},
        {"containers": ["api"], "ports": [4189], "health": "failed", "evidence": ["log-error"]},
    )
    assert result["passed"] is False
    assert result["rollback_recommended"] is True


def test_catalog_is_typed():
    result = catalog()
    assert result["execution"] == "delegated_to_terminall"
    assert "compose_restart" in result["operations"]
