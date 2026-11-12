"""Deterministic Godot 4 starter generator. No network, AI, shell or live source writes."""
import json
import re
from pathlib import Path

DIMENSIONS=("2d","3d")
GENRES=("sandbox","survival","strategy","economy","platformer")
PLATFORMS=("android","web","pc")
CONTROLS=("touch","keyboard_mouse","gamepad")
SYSTEMS=("movement","camera","economy","inventory","day_night")
VALID_ID=re.compile(r"[a-z][a-z0-9-]{2,39}\Z")

def validate(config):
    if not isinstance(config,dict) or set(config)!={"title","dimension","genre","platforms","controls","systems"}:
        raise ValueError("invalid_wizard_config")
    title=config["title"]
    if not isinstance(title,str) or not 1<=len(title)<=70 or any(ord(c)<32 or c in '\\/<>"' for c in title):
        raise ValueError("invalid_title")
    if config["dimension"] not in DIMENSIONS or config["genre"] not in GENRES or config["controls"] not in CONTROLS:
        raise ValueError("unsupported_wizard_option")
    for key,allowed in (("platforms",PLATFORMS),("systems",SYSTEMS)):
        values=config[key]
        if not isinstance(values,list) or not values or len(values)>len(allowed) or len(values)!=len(set(map(str,values))) or any(not isinstance(v,str) or v not in allowed for v in values):
            raise ValueError("invalid_"+key)
    if config["controls"]=="touch" and "android" not in config["platforms"]:
        raise ValueError("touch_requires_android")
    if config["dimension"]=="3d" and config["genre"]=="platformer":
        # This starter intentionally implements only a 2D platformer.
        raise ValueError("platformer_template_requires_2d")
    return config

def generate(folder,config):
    config=validate(config)
    root=Path(folder)
    root.mkdir(parents=True,exist_ok=True)
    (root/"scenes").mkdir()
    (root/"scripts").mkdir()
    dimension=config["dimension"]
    three=dimension=="3d"
    renderer="gl_compatibility" if "android" in config["platforms"] or "web" in config["platforms"] else "gl_compatibility"
    title=config["title"].replace('"',"'")
    settings=('config_version=5\n\n[application]\nconfig/name="'+title+
              '"\nrun/main_scene="res://scenes/main.tscn"\nconfig/features=PackedStringArray("GL Compatibility")\n\n'+
              '[rendering]\nrenderer/rendering_method="'+renderer+'"\nrenderer/rendering_method.mobile="'+renderer+'"\n')
    if "movement" in config["systems"]:
        settings+='\n[input]\nmove_left={"deadzone":0.2,"events":[] }\nmove_right={"deadzone":0.2,"events":[] }\n'
    (root/"project.godot").write_text(settings)
    node="Node3D" if three else "Node2D"
    camera="Camera3D" if three else "Camera2D"
    scene=['[gd_scene load_steps=2 format=3]','',
           '[ext_resource type="Script" path="res://scripts/main.gd" id="1"]','',
           '[node name="Main" type="'+node+'"]','script = ExtResource("1")','']
    if "camera" in config["systems"]:
        scene+=['[node name="Camera" type="'+camera+'" parent="."]',
                'current = true','']
    if "movement" in config["systems"]:
        scene+=['[node name="Player" type="'+node+'" parent="."]','']
    (root/"scenes"/"main.tscn").write_text("\n".join(scene))
    script=['extends '+node,'','## Generated deterministic '+config["genre"]+' starter.','## Replace placeholder logic in an isolated development branch.','']
    if "economy" in config["systems"]:
        script+=['var money: int = 1000','var income_per_tick: int = 10','']
    if "inventory" in config["systems"]:
        script+=['var inventory: Dictionary = {}','']
    if "day_night" in config["systems"]:
        script+=['var time_of_day: float = 8.0','']
    script+=['func _process(delta: float) -> void:']
    if "day_night" in config["systems"]:
        script+=['\ttime_of_day = fmod(time_of_day + delta * 0.1, 24.0)']
    else:
        script+=['\tpass']
    script+=['']
    if "economy" in config["systems"]:
        script+=['func economy_tick() -> void:','\tmoney += income_per_tick','']
    if "inventory" in config["systems"]:
        script+=['func add_item(item_id: String, count: int = 1) -> void:',
                 '\tif count > 0:','\t\tinventory[item_id] = int(inventory.get(item_id, 0)) + count','']
    if "movement" in config["systems"]:
        script+=['var move_speed: float = 200.0','']
        script+=['func _physics_process(delta: float) -> void:',
                 '\tvar direction := Vector2.ZERO',
                 '\tif Input.is_action_pressed("ui_left"): direction.x -= 1.0',
                 '\tif Input.is_action_pressed("ui_right"): direction.x += 1.0',
                 '\tif Input.is_action_pressed("ui_up"): direction.y -= 1.0',
                 '\tif Input.is_action_pressed("ui_down"): direction.y += 1.0']
        if three:
            script+=['\t$Player.position += Vector3(direction.x, 0.0, direction.y).normalized() * move_speed * delta']
        else:
            script+=['\t$Player.position += direction.normalized() * move_speed * delta']
        script+=['']
    (root/"scripts"/"main.gd").write_text("\n".join(script))
    if "android" in config["platforms"]:
        from godot_mobile_quality import add_quality_menu
        add_quality_menu(root)
    (root/"wizard.json").write_text(json.dumps(config,ensure_ascii=False,indent=2))
    return {"dimension":dimension,"genre":config["genre"],"platforms":config["platforms"],
            "controls":config["controls"],"systems":config["systems"],"template_only":True}
