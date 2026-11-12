from nexus.godot_glb_audit import assess_gltf
from nexus.mcp_principal import principal_var
from nexus.mcp_server import nexus_meshy_prepare_refine
import pytest

def test_valid_gltf_audit():
    result=assess_gltf({"asset":{"version":"2.0"},"meshes":[{"primitives":[{}]}],"nodes":[{}]})
    assert result["mesh_count"]==1
    assert result["primitive_count"]==1
    assert result["optimized"] is False
    assert result["geometry_verified"] is False

def test_invalid_gltf_audit():
    assert assess_gltf({"asset":{"version":"1.0"}})["error"]=="invalid_gltf_2"
    assert assess_gltf({"asset":{"version":"2.0"},"meshes":"bad"})["error"]=="invalid_collections"

def test_gltf_mobile_warnings():
    result=assess_gltf({"asset":{"version":"2.0"},"textures":[{}]*33,
        "extensionsRequired":["UNKNOWN_extension"]})
    assert "excessive_textures" in result["warnings"]
    assert "check_godot_extension_compatibility" in result["warnings"]

def test_refine_prepare_denies_anonymous():
    token=principal_var.set(None)
    try:
        with pytest.raises(PermissionError):
            nexus_meshy_prepare_refine("00000000-0000-0000-0000-000000000001")
    finally:
        principal_var.reset(token)

def test_refine_prepare_rejects_invalid_without_db():
    token=principal_var.set({"user_id":"user","scope":"mcp:read","roles":["owner"]})
    try:
        assert nexus_meshy_prepare_refine("invalid")["error"]=="invalid_preview_request_id"
        assert nexus_meshy_prepare_refine("00000000-0000-0000-0000-000000000001",9)["error"]=="invalid_credit_ceiling"
    finally:
        principal_var.reset(token)
