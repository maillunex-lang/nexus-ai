import importlib.util
from pathlib import Path
import pytest

SCRIPT=Path(__file__).resolve().parents[2]/"scripts"/"run_godot_glb_pipeline.py"

def load():
    spec=importlib.util.spec_from_file_location("offline_glb_pipeline",SCRIPT)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_runner_rejects_identical_paths(tmp_path):
    runner=load()
    source=tmp_path/"test.glb"
    source.write_bytes(b"invalid")
    with pytest.raises(ValueError,match="different GLB"):
        runner.run(source,source)

def test_runner_rejects_invalid_glb_before_blender(tmp_path):
    runner=load()
    source=tmp_path/"bad.glb"
    source.write_bytes(b"invalid")
    with pytest.raises(ValueError,match="Invalid source GLB"):
        runner.run(source,tmp_path/"output.glb")

def test_runner_does_not_overwrite_output(tmp_path):
    runner=load()
    source=tmp_path/"source.glb"
    target=tmp_path/"target.glb"
    source.write_bytes(b"invalid")
    target.write_bytes(b"existing")
    with pytest.raises(ValueError,match="Output must not exist"):
        runner.run(source,target)
    assert target.read_bytes()==b"existing"
