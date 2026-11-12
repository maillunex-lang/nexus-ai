import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import pytest

SCRIPT=Path("/scripts/godot_android_build.py")
if not SCRIPT.exists():
    SCRIPT=Path(__file__).resolve().parents[2]/"scripts/godot_android_build.py"
spec=importlib.util.spec_from_file_location("godot_android_build",SCRIPT)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

JOB="godot-"+"a"*32

def test_reject_invalid_id():
    with pytest.raises(ValueError,match="invalid_job_id"):
        module.build("../etc/passwd")

def test_reject_unvalidated_workspace(tmp_path):
    folder=tmp_path/JOB
    folder.mkdir()
    (folder/"nexus_godot_report.json").write_text(json.dumps({"job_id":JOB,"passed":False}))
    with patch.object(module,"ROOT",tmp_path):
        with pytest.raises(ValueError,match="validation_not_passed"):
            module.build(JOB)

def test_reject_missing_android_preset(tmp_path):
    folder=tmp_path/JOB
    folder.mkdir()
    (folder/"nexus_godot_report.json").write_text(json.dumps({"job_id":JOB,"passed":True}))
    with patch.object(module,"ROOT",tmp_path):
        with pytest.raises(ValueError,match="android_preset_unavailable"):
            module.build(JOB)

def test_reject_symlink_workspace(tmp_path):
    real=tmp_path/"real"
    real.mkdir()
    (real/"nexus_godot_report.json").write_text(json.dumps({"job_id":JOB,"passed":True}))
    (tmp_path/JOB).symlink_to(real,target_is_directory=True)
    with patch.object(module,"ROOT",tmp_path):
        with pytest.raises(ValueError,match="workspace_unavailable"):
            module.build(JOB)
