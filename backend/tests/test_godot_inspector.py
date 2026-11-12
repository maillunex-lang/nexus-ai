from nexus.godot_inspector import inspect_gdscript,inspect_shader,MAX_SOURCE

def test_script_inspection_is_read_only():
    r=inspect_gdscript("extends Node\nfunc _process(delta):\n  var n = get_node('A')\n")
    assert r["modified"] is False and r["execution_enabled"] is False
    assert any(f["code"]=="node_lookup" for f in r["findings"])

def test_shader_mobile_findings():
    r=inspect_shader("shader_type canvas_item;\nvoid fragment() { discard; COLOR=vec4(sin(UV.x)); }")
    assert r["execution_enabled"] is False
    assert {x["code"] for x in r["findings"]}>={"discard","expensive_math"}

def test_limits_and_filename_validation():
    assert inspect_gdscript("x"*(MAX_SOURCE+1))["error"]=="source_too_large"
    assert inspect_shader("x"*(MAX_SOURCE+1))["error"]=="source_too_large"
    assert inspect_gdscript("pass","../secret.gd")["error"]=="invalid_filename"
    assert inspect_shader("pass","/etc/a.gdshader")["error"]=="invalid_filename"

def test_empty_source_is_safe():
    assert inspect_gdscript("")["findings"]==[]
    assert inspect_shader("")["findings"]==[{"code":"missing_shader_type","severity":"warning","message":"Не указан shader_type."}]
