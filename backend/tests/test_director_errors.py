from unittest.mock import patch
import pytest
from nexus import director_errors as e
from nexus.mcp_principal import principal_var

GODOT_LOG = """Godot Engine v4.7.2.stable
SCRIPT ERROR: Parse Error: Expected ":" after "if" condition.
          at: GDScript::reload (res://scripts/player.gd:12)
ERROR: Failed to load script "res://scripts/player.gd" with error "Parse error".
   at: load (modules/gdscript/gdscript.cpp:2936)
SCRIPT ERROR: Parse Error: Expected ":" after "if" condition.
          at: GDScript::reload (res://scripts/player.gd:12)
"""


def test_classification_policies():
    assert e.classify("ValueError:godot_validation_failed:...")["category"] == "godot_validation_failed"
    assert e.classify("verification_blocked")["policy"] == "reject_without_retry"
    assert e.classify("ValueError:android_preset_unavailable")["retryable"] is False
    assert e.classify("worker_timeout")["retryable"] is True
    assert e.classify("ValueError:export_templates_unavailable")["category"] == "toolchain_unavailable"
    assert e.classify("something new")["category"] == "unknown"
    assert all(e.classify(x)["auto_retry"] is False for x in ("worker_timeout", "build_failed", ""))


def test_godot_diagnostics_are_structured_and_deduplicated():
    found = e.diagnostics(GODOT_LOG)
    assert found[0] == {"kind": "script_error", "message": 'Parse Error: Expected ":" after "if" condition.',
                        "file": "scripts/player.gd", "line": 12}
    assert found[1]["kind"] == "engine_error" and found[1]["file"] == "scripts/player.gd"
    assert len(found) == 2
    assert e.diagnostics("") == [] and e.diagnostics(None) == []


def test_journal_is_owner_scoped_filtered_and_rotated(tmp_path):
    with patch.object(e, "ROOT", tmp_path):
        e.record("owner-1", source="pipeline", project_id="basheco", stage="validate_change",
                 error="godot_validation_failed", detail=GODOT_LOG, reference="pipe-1", agent="tester")
        e.record("owner-1", source="pipeline", project_id="watermmo", stage="build", error="worker_timeout")
        e.record("owner-2", source="pipeline", project_id="basheco", stage="build", error="build_failed")
        assert not any("owner" in p.name for p in tmp_path.iterdir())
        token = principal_var.set({"user_id": "owner-1", "roles": ["owner"], "scope": "mcp:read"})
        try:
            result = e.list_errors()
            assert [x["stage"] for x in result["errors"]] == ["build", "validate_change"]
            assert result["by_category"] == {"godot_validation_failed": 1, "worker_timeout": 1}
            assert result["errors"][1]["diagnostics"][0]["line"] == 12
            assert len(e.list_errors(project_id="watermmo")["errors"]) == 1
            assert e.list_errors(limit=0)["error"] == "invalid_limit"
            with patch.object(e, "MAX_JOURNAL_BYTES", 10):
                e.record("owner-1", source="pipeline", project_id="basheco", stage="build", error="build_failed")
            assert len(e.list_errors()["errors"]) == 1
            assert len(list(tmp_path.glob("*.jsonl.1"))) == 1
        finally:
            principal_var.reset(token)


def test_journal_requires_owner(tmp_path):
    with patch.object(e, "ROOT", tmp_path), pytest.raises(PermissionError):
        e.list_errors()
