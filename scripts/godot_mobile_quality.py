"""Generate optional Android quality menu in isolated new Godot wizard projects."""
from pathlib import Path

QUALITY_SCRIPT='''extends CanvasLayer

const SAVE_PATH := "user://graphics_settings.cfg"
const LEVELS := ["Очень низкие", "Низкие", "Средние", "Высокие"]
const FPS := [30, 30, 45, 60]
const SCALES := [0.65, 0.8, 1.0, 1.0]

var selected_level: int = 1
var panel: PanelContainer
var selector: OptionButton
var fps_label: Label

func _ready() -> void:
    _load_settings()
    _create_ui()
    _apply_quality()
    panel.visible = false

func _create_ui() -> void:
    var toggle := Button.new()
    toggle.text = "Графика"
    toggle.position = Vector2(16, 16)
    toggle.pressed.connect(_toggle)
    add_child(toggle)
    panel = PanelContainer.new()
    panel.position = Vector2(16, 64)
    add_child(panel)
    var layout := VBoxContainer.new()
    panel.add_child(layout)
    var title := Label.new()
    title.text = "Настройки графики"
    layout.add_child(title)
    selector = OptionButton.new()
    for name in LEVELS:
        selector.add_item(name)
    selector.select(selected_level)
    selector.item_selected.connect(_on_level_selected)
    layout.add_child(selector)
    fps_label = Label.new()
    layout.add_child(fps_label)
    var close := Button.new()
    close.text = "Закрыть"
    close.pressed.connect(_toggle)
    layout.add_child(close)

func _toggle() -> void:
    panel.visible = not panel.visible

func _on_level_selected(index: int) -> void:
    selected_level = clampi(index, 0, LEVELS.size() - 1)
    _apply_quality()
    _save_settings()

func _apply_quality() -> void:
    Engine.max_fps = FPS[selected_level]
    if fps_label != null:
        fps_label.text = "Лимит FPS: %d" % FPS[selected_level]
    # 3D scaling and optional effects must be integrated per renderer/scene.
    # No unsupported global scale setting is applied.

func _load_settings() -> void:
    var cfg := ConfigFile.new()
    if cfg.load(SAVE_PATH) == OK:
        selected_level = clampi(int(cfg.get_value("graphics", "level", 1)), 0, 3)

func _save_settings() -> void:
    var cfg := ConfigFile.new()
    cfg.set_value("graphics", "level", selected_level)
    cfg.save(SAVE_PATH)
'''

def add_quality_menu(folder):
    root=Path(folder)
    scripts=root/"scripts"
    scripts.mkdir(exist_ok=True)
    (scripts/"graphics_menu.gd").write_text(QUALITY_SCRIPT)
    scene=root/"scenes"/"main.tscn"
    source=scene.read_text()
    source=source.replace("load_steps=2","load_steps=3",1)
    source=source.replace('[node name="Main"', '[ext_resource type="Script" path="res://scripts/graphics_menu.gd" id="2"]\n\n[node name="Main"',1)
    source+='\n[node name="GraphicsMenu" type="CanvasLayer" parent="."]\nscript = ExtResource("2")\n'
    scene.write_text(source)
    return {"graphics_menu":True,"fps_limit":True,"persistent_quality_choice":True,
            "dynamic_resolution":False,"particle_switching":False}
