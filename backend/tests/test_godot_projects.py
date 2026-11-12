from pathlib import Path
from unittest.mock import patch
from nexus import godot_projects as gp

def test_unknown_project_fails_closed():
    assert gp.inspect_project("other")["error"]=="unknown_project"
    assert gp.inspect_file("other","a.gd")["error"]=="unknown_project"

def test_inventory_and_file_inspection(tmp_path):
    (tmp_path/"project.godot").write_text('[application]\nconfig/name="Test"\nrun/main_scene="res://main.tscn"\n')
    (tmp_path/"main.tscn").write_text('[gd_scene format=3]\n[node name="Root" type="Node2D"]\n')
    (tmp_path/"main.gd").write_text('extends Node\nfunc _process(delta):\n  get_node("A")\n')
    (tmp_path/"water.gdshader").write_text('shader_type canvas_item; void fragment() { discard; }')
    with patch.dict(gp.PROJECTS,{"test":{"name":"Test","root":str(tmp_path)}}):
        result=gp.inspect_project("test",True)
        assert result["counts"]=={"scene":1,"script":1,"shader":1,"resource":0}
        assert result["scene_nodes"]==1
        assert any(x["code"]=="node_lookup" for x in result["findings"])
        assert gp.inspect_file("test","main.gd")["analysis"]["execution_enabled"] is False
        assert gp.inspect_file("test","water.gdshader")["analysis"]["findings"][0]["code"]=="discard"

def test_traversal_and_symlinks_rejected(tmp_path):
    (tmp_path/"project.godot").write_text("[application]\n")
    outside=tmp_path.parent/"secret.gd"
    (tmp_path/"link.gd").symlink_to(outside)
    with patch.dict(gp.PROJECTS,{"test":{"name":"Test","root":str(tmp_path)}}):
        for path in ("../secret.gd","/etc/passwd","x/../../secret.gd",".git/config","x\\a.gd"):
            assert gp.inspect_file("test",path)["error"]=="invalid_path"
        assert gp.inspect_file("test","link.gd")["error"]=="not_found" or gp.inspect_file("test","link.gd")["error"]=="unreadable_or_symlink"

def test_large_files_skipped(tmp_path):
    (tmp_path/"project.godot").write_text("[application]\n")
    (tmp_path/"large.gd").write_bytes(b"x"*(gp.MAX_BYTES+1))
    with patch.dict(gp.PROJECTS,{"test":{"name":"Test","root":str(tmp_path)}}):
        assert gp.inspect_file("test","large.gd")["error"]=="file_too_large"
        assert gp.inspect_project("test")["skipped_large_or_unreadable"]==1
