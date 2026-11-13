from nexus import director_verification as v


def codes(checks):
    return {c["code"] for c in checks}


def test_valid_gdscript_passes():
    source = 'extends Node\n\nfunc _ready():\n\tvar a = {"k": [1, 2, (3)]}\n\tprint("text ) with # bracket")  # comment (\n'
    assert v.check_gdscript(source) == []
    assert v.verify([{"path": "a.gd", "old": "", "new": source}])["verdict"] == "pass"


def test_brackets_and_strings_block():
    assert "unbalanced_brackets" in codes(v.check_gdscript("func a():\n\tprint((1)\n"))
    assert "unbalanced_brackets" in codes(v.check_gdscript("func a():\n\tprint(1))\n"))
    assert "unterminated_string" in codes(v.check_gdscript('var a = "open\n'))
    multiline = 'var a = """line (\nsecond ]"""\nvar b = r"raw \\"\n'
    assert v.check_gdscript(multiline) == []


def test_mixed_indentation_blocks_but_continuation_lines_do_not():
    assert "mixed_indentation" in codes(v.check_gdscript("func a():\n\tpass\nfunc b():\n    pass\n"))
    continuation = "func a():\n\tvar x = [\n        1,\n        2,\n\t]\n\treturn x\n"
    assert v.check_gdscript(continuation) == []


def test_new_process_api_blocks_and_existing_is_not_repeated():
    risky = 'func a():\n\tOS.execute("sh", [])\n'
    assert "process_execution_api" in codes(v.check_gdscript(risky, "func a():\n\tpass\n"))
    assert v.check_gdscript(risky, risky) == []
    assert v.check_gdscript('func a():\n\tprint("OS.execute(")\n\t# OS.execute(\n') == []


def test_network_api_warns():
    result = v.verify([{"path": "net.gd", "old": "extends Node\n", "new": "extends Node\nvar h = HTTPRequest.new()\n"}])
    assert result["verdict"] == "warn" and result["warnings"] == 1 and result["blocking"] == 0


def test_resources_and_shaders():
    scene = '[gd_scene format=3]\n[ext_resource type="Script" path="res://a.gd" id="1"]\n[ext_resource type="Script" path="res://gone.gd" id="2"]\n'
    found = v.check_resource(scene, ".tscn", lambda rel: rel == "a.gd")
    assert [c["code"] for c in found] == ["missing_ext_resource"] and "gone.gd" in found[0]["message"]
    assert "missing_resource_header" in codes(v.check_resource("[node]\n", ".tscn"))
    assert v.check_resource("[gd_resource type=\"Theme\"]\n", ".tres") == []
    assert v.check_shader("shader_type canvas_item;\nvoid fragment(){ COLOR = vec4(1.0); } // )\n") == []
    assert codes(v.check_shader("// shader_type spatial;\nvoid fragment(){\n")) == {"missing_shader_type", "unbalanced_brackets"}


def test_common_rules_and_verdict():
    result = v.verify([
        {"path": "a.gd", "old": "x" * 3000, "new": "extends Node\n"},
        {"path": "b.gd", "old": "", "new": "<<<<<<< HEAD\nextends Node\n"},
        {"path": "c.tres", "old": "[gd_resource]\n", "new": "  \n"},
    ])
    assert result["verdict"] == "block"
    assert {"large_deletion", "merge_conflict_marker", "empty_file"} <= codes(result["checks"])
    assert all(c["path"] for c in result["checks"])
    assert result["godot_executed"] is False
