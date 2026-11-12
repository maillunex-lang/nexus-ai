import json
import sys
from pathlib import Path
from unittest.mock import patch
from nexus import godot_project_onboarding as onboarding
from nexus.mcp_principal import principal_var
sys.path.insert(0,"/scripts")
from godot_game_wizard import generate,validate

def config(**overrides):
 data={"title":"My Game","dimension":"2d","genre":"economy","platforms":["android","web"],"controls":"touch","systems":["movement","camera","economy","inventory","day_night"]}
 data.update(overrides)
 return data

def test_2d_and_3d_generate_valid_structure(tmp_path):
 for dimension in ("2d","3d"):
  folder=tmp_path/dimension
  result=generate(folder,config(dimension=dimension))
  assert (folder/"project.godot").exists()
  assert "Node3D" in (folder/"scenes/main.tscn").read_text() if dimension=="3d" else "Node2D" in (folder/"scenes/main.tscn").read_text()
  assert "economy_tick" in (folder/"scripts/main.gd").read_text()
  assert result["template_only"]

def test_invalid_options_rejected():
 for c in (config(genre="unknown"),config(platforms=["pc","pc"]),config(controls="touch",platforms=["pc"]),config(dimension="3d",genre="platformer")):
  try:validate(c)
  except ValueError:pass
  else:assert False

def test_wizard_requires_owner_and_does_not_enable_build(tmp_path):
 t=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:write"})
 try:
  with patch.object(onboarding,"QUEUE",tmp_path):
   result=onboarding.request("wizard-test","wizard",json.dumps(config()))
   assert result["state"]=="queued" and result["build_enabled"] is False
   assert onboarding.request("wizard-test","wizard",json.dumps(config(genre="invalid")))["error"]=="invalid_wizard_choice"
 finally:principal_var.reset(t)
