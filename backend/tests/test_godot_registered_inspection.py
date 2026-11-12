import json
from unittest.mock import patch
from nexus import godot_projects as projects
from nexus import godot_one_command as one
from nexus.mcp_principal import principal_var

def test_registered_project_is_inspection_only(tmp_path):
    folder=tmp_path/"new-game"
    source=folder/"source"
    source.mkdir(parents=True)
    (source/"project.godot").write_text('[application]\nconfig/name="New Game"\n')
    (folder/"manifest.json").write_text(json.dumps({"project_id":"new-game","build_enabled":False}))
    original=projects.Path
    with patch.object(projects,"Path",side_effect=lambda value: original(tmp_path) if value=="/registered-projects" else original(value)):
        report=projects.inspect_project("new-game")
        assert report["read_only"] and report["project_id"]=="new-game"
        t=principal_var.set({"user_id":"owner","roles":["owner"],"scope":"mcp:write"})
        try:
            assert one.start("new-game")["error"]=="unknown_or_unconfigured_project"
        finally:principal_var.reset(t)
