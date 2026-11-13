import hashlib
import sys
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
    with patch.object(mod.shutil,"which",return_value=sys.executable),patch.object(mod.subprocess,"run",return_value=Result()) as process:
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

def _result(stdout="ok",code=0):
    class Result:
        stderr=""
        returncode=code
    Result.stdout=stdout
    return Result()

def _two_files(tmp_path):
    root,content=project(tmp_path)
    (root/"other.gd").write_text("extends Node2D\n")
    parent=tmp_path/"work"
    parent.mkdir()
    patches=[{"path":"main.gd","expected_sha256":hashlib.sha256(content.encode()).hexdigest(),"content":"extends Node\nvar a=1\n"},
             {"path":"other.gd","expected_sha256":hashlib.sha256(b"extends Node2D\n").hexdigest(),"content":"extends Node2D\nvar b=2\n"}]
    return root,parent,patches

def test_multi_file_patch_applies_only_to_copy(tmp_path):
    root,parent,patches=_two_files(tmp_path)
    with patch.object(mod.shutil,"which",return_value=sys.executable),patch.object(mod.subprocess,"run",return_value=_result()):
        report=mod.run(root,parent,patches)
    assert report["passed"] and report["patched_files"]==2
    assert (root/"main.gd").read_text()=="extends Node\n" and (root/"other.gd").read_text()=="extends Node2D\n"
    assert (Path(report["workspace"])/"other.gd").read_text()=="extends Node2D\nvar b=2\n"

def test_multi_file_patch_is_all_or_nothing(tmp_path):
    root,parent,patches=_two_files(tmp_path)
    patches[1]["expected_sha256"]="0"*64
    with pytest.raises(ValueError,match="source_changed"):
        mod.run(root,parent,patches)
    assert not list(parent.iterdir())
    with pytest.raises(ValueError,match="duplicate_patch_path"):
        mod.verify_patch(root,[patches[0],patches[0]])
    with pytest.raises(ValueError,match="invalid_patch"):
        mod.verify_patch(root,[patches[0]]*9)
    with pytest.raises(ValueError,match="invalid_patch"):
        mod.verify_patch(root,[])

def test_script_errors_fail_patched_copy_but_not_unpatched_build(tmp_path):
    root,parent,patches=_two_files(tmp_path)
    log='SCRIPT ERROR: Parse Error: Expected ":"\n   at: GDScript::reload (res://main.gd:2)\nERROR: Failed to load script\n'
    with patch.object(mod.shutil,"which",return_value=sys.executable),patch.object(mod.subprocess,"run",return_value=_result(log)):
        patched=mod.run(root,parent,patches[0])
        plain=mod.run(root,parent)
    assert patched["godot_script_errors"]==1 and patched["godot_errors"]==2 and not patched["passed"]
    assert plain["godot_script_errors"]==1 and plain["passed"]

def test_create_and_delete_operations_only_touch_the_copy(tmp_path):
    root,parent,patches=_two_files(tmp_path)
    operations=[patches[0],
                {"action":"create","path":"ui/new/hud.gd","content":"extends Control\n"},
                {"action":"delete","path":"other.gd","expected_sha256":hashlib.sha256(b"extends Node2D\n").hexdigest()}]
    with patch.object(mod.shutil,"which",return_value=sys.executable),patch.object(mod.subprocess,"run",return_value=_result()):
        report=mod.run(root,parent,operations)
    workspace=Path(report["workspace"])
    assert report["passed"] and report["patched_files"]==3
    assert (workspace/"ui/new/hud.gd").read_text()=="extends Control\n" and not (workspace/"other.gd").exists()
    assert (root/"other.gd").exists() and not (root/"ui").exists()

def test_create_and_delete_are_validated_before_any_copy(tmp_path):
    root,parent,patches=_two_files(tmp_path)
    for operation,error in (({"action":"create","path":"main.gd","content":"x"},"file_already_exists"),
                            ({"action":"create","path":"../evil.gd","content":"x"},"invalid_path"),
                            ({"action":"create","path":"main.gd/child.gd","content":"x"},"invalid_path"),
                            ({"action":"create","path":"run.sh","content":"x"},"unsupported_file_type"),
                            ({"action":"create","path":".git/hook.gd","content":"x"},"invalid_path"),
                            ({"action":"delete","path":"other.gd","expected_sha256":"0"*64},"source_changed"),
                            ({"action":"delete","path":"project.godot","expected_sha256":"0"*64},"unsupported_file_type"),
                            ({"action":"delete","path":"other.gd","expected_sha256":"0"*64,"content":"x"},"invalid_patch"),
                            ({"action":"chmod","path":"other.gd"},"invalid_patch")):
        with pytest.raises(ValueError,match=error):
            mod.run(root,parent,[operation])
    assert not list(parent.iterdir())
    (root/"link").symlink_to(tmp_path)
    with pytest.raises(ValueError,match="symlink_rejected"):
        mod.verify_patch(root,[{"action":"create","path":"link/x.gd","content":"x"}])
