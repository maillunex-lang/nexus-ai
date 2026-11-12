from unittest.mock import patch
from nexus import graphics_enhancer as g
from nexus.mcp_principal import principal_var

def test_2d_compatibility_and_profile(tmp_path):
 (tmp_path/"project.godot").write_text('[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
 (tmp_path/"main.tscn").write_text('[node name="Main" type="Node2D"]\n[node name="Rain" type="GPUParticles2D"]')
 (tmp_path/"sprite.png").write_bytes(b"test")
 t=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:read"})
 try:
  with patch.object(g,"_root",return_value=tmp_path):
   result=g.audit("test","low")
   assert result["dimension"]=="2d" and result["assets"]["images"]==1
   assert result["features_detected"]["particles"] and not result["applied"]
   assert "vignette_2d" in [x["effect"] for x in result["recommendations"]]
   assert g.audit("test","ultra")["error"]=="unknown_profile"
 finally:principal_var.reset(t)

def test_3d_and_no_anonymous_access(tmp_path):
 (tmp_path/"project.godot").write_text('config_version=5')
 (tmp_path/"world.tscn").write_text('[node name="World" type="Node3D"]')
 t=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:read"})
 try:
  with patch.object(g,"_root",return_value=tmp_path):
   result=g.audit("test")
   assert result["dimension"]=="3d"
   assert "water_fresnel" in [x["effect"] for x in result["recommendations"]]
 finally:principal_var.reset(t)
 try:g.catalog()
 except PermissionError:pass
 else:assert False
