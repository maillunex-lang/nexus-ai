import hashlib
from unittest.mock import patch
from nexus import godot_projects as gp
from nexus.godot_change_preview import preview

def setup(tmp_path):
    (tmp_path/"project.godot").write_text("[application]\n")
    original="extends Node\nfunc _ready():\n    pass\n"
    (tmp_path/"main.gd").write_text(original)
    return original,hashlib.sha256(original.encode()).hexdigest()

def test_sha_pinned_diff_no_mutation(tmp_path):
    old,sha=setup(tmp_path)
    with patch.dict(gp.PROJECTS,{"test":{"name":"Test","root":str(tmp_path)}}):
        result=preview("test","main.gd",sha,"extends Node\nfunc _ready():\n    print('ok')\n")
    assert result["changed"] and not result["applied"]
    assert "+    print('ok')" in result["diff"]
    assert (tmp_path/"main.gd").read_text()==old

def test_stale_sha_rejected(tmp_path):
    old,sha=setup(tmp_path)
    with patch.dict(gp.PROJECTS,{"test":{"name":"Test","root":str(tmp_path)}}):
        assert preview("test","main.gd","0"*64,"extends Node")["error"]=="source_changed"

def test_symlink_and_traversal_rejected(tmp_path):
    old,sha=setup(tmp_path)
    (tmp_path/"linked.gd").symlink_to(tmp_path/"main.gd")
    with patch.dict(gp.PROJECTS,{"test":{"name":"Test","root":str(tmp_path)}}):
        assert preview("test","../main.gd",sha,"hello")["error"]=="invalid_path"
        assert preview("test","linked.gd",sha,"hello")["error"]=="unreadable_or_symlink"

def test_scene_header_warning(tmp_path):
    old,sha=setup(tmp_path)
    source="[gd_scene format=3]\n"
    (tmp_path/"level.tscn").write_text(source)
    digest=hashlib.sha256(source.encode()).hexdigest()
    with patch.dict(gp.PROJECTS,{"test":{"name":"Test","root":str(tmp_path)}}):
        result=preview("test","level.tscn",digest,"invalid")
    assert result["findings"][0]["code"]=="missing_resource_header"
