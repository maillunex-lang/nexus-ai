from unittest.mock import patch
from nexus import android_optimizer as opt
from nexus.mcp_principal import principal_var

def test_android_audit_is_read_only(tmp_path):
 (tmp_path/"project.godot").write_text("config_version=5")
 (tmp_path/"main.tscn").write_text('[node name="Particles" type="GPUParticles2D"]\n')
 (tmp_path/"big.png").write_bytes(b"0"*4_000_001)
 t=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:read"})
 try:
  with patch.object(opt,"_root",return_value=tmp_path):
   result=opt.inspect("example")
   assert result["inventory"]["large_textures"]==1
   assert result["inventory"]["particles"]==1
   assert result["source_modified"] is False
   assert result["device_fps_measured"] is False
   assert len(opt.presets()["presets"])==4
 finally:principal_var.reset(t)
