import hashlib
import importlib.util
from pathlib import Path
from unittest.mock import patch
import pytest

SCRIPT=Path("/scripts/godot_agent_workspace.py")
if not SCRIPT.exists():
    SCRIPT=Path(__file__).resolve().parents[2]/"scripts/godot_agent_workspace.py"
spec=importlib.util.spec_from_file_location("godot_agent_workspace",SCRIPT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def project(tmp_path):
    root=tmp_path/"source"
    root.mkdir()
    (root/"project.godot").write_text('[application]\nconfig/name="Test"\n')
    content="extends Node\n"
    (root/"main.gd").write_text(content)
    return root,content

def test_copy_patch_and_no_original_mutation(tmp_path):
    root,content=project(tmp_path)
    parent=tmp_path/"work"
    parent.mkdir()
    proposed="extends Node\nfunc _ready(): pass\n"
    change={"path":"main.gd","expected_sha256":hashlib.sha256(content.encode()).hexdigest(),"content":proposed}
    class Result:
        stdout="ok"
        stderr=""
        returncode=0
    with patch.object(mod.shutil,"which",return_value="/usr/local/bin/python"),patch.object(mod.subprocess,"run",return_value=Result()) as process:
        report=mod.run(root,parent,change)
    assert report["passed"]
    assert report["patch_applied_to_copy"]
    assert (root/"main.gd").read_text()==content
    assert (Path(report["workspace"])/"main.gd").read_text()==proposed
    assert (Path(report["workspace"])/"nexus_godot_report.json").exists()
    assert "--headless" in process.call_args.args[0]

def test_stale_sha_fails_before_workspace(tmp_path):
    root,_=project(tmp_path)
    parent=tmp_path/"work"
    parent.mkdir()
    with pytest.raises(ValueError,match="source_changed"):
        mod.run(root,parent,{"path":"main.gd","expected_sha256":"0"*64,"content":"changed"})
    assert not list(parent.iterdir())

def test_reject_symlink_in_source(tmp_path):
    root,_=project(tmp_path)
    (root/"link.gd").symlink_to(root/"main.gd")
    with pytest.raises(ValueError,match="symlink_in_source"):
        mod.source_manifest(root)

def test_reject_workspace_inside_project(tmp_path):
    root,_=project(tmp_path)
    with pytest.raises(ValueError,match="workspace_must_be_separate"):
        mod.run(root,root)

def test_reject_traversal(tmp_path):
    root,_=project(tmp_path)
    with pytest.raises(ValueError,match="invalid_path"):
        mod.verify_patch(root,{"path":"../main.gd","expected_sha256":"0"*64,"content":"x"})
