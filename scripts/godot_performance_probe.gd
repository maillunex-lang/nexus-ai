extends SceneTree

var elapsed := 0.0
var warmup := 2.0
var duration := 10.0
var frames := 0
var frame_ms: Array[float] = []
var process_ms: Array[float] = []
var memory_peak := 0.0
var nodes_peak := 0.0

func _initialize() -> void:
    for arg in OS.get_cmdline_user_args():
        if arg.begins_with("duration="):
            duration = clampf(float(arg.trim_prefix("duration=")), 5.0, 60.0)
    # Bound CPU consumption for uncapped games; retain any lower game cap.
    if Engine.max_fps == 0 or Engine.max_fps > 60:
        Engine.max_fps = 60
    var main_scene: String = ProjectSettings.get_setting("application/run/main_scene", "")
    if main_scene.is_empty():
        quit(2)
        return
    if change_scene_to_file(main_scene) != OK:
        quit(2)

func _process(delta: float) -> bool:
    elapsed += delta
    if elapsed < warmup:
        return false
    frames += 1
    frame_ms.append(delta * 1000.0)
    process_ms.append(float(Performance.get_monitor(Performance.TIME_PROCESS)) * 1000.0)
    memory_peak = maxf(memory_peak, float(Performance.get_monitor(Performance.MEMORY_STATIC)))
    nodes_peak = maxf(nodes_peak, float(Performance.get_monitor(Performance.OBJECT_NODE_COUNT)))
    if elapsed >= warmup + duration:
        frame_ms.sort()
        process_ms.sort()
        var p95 := mini(int(frame_ms.size() * 0.95), frame_ms.size() - 1)
        print("NEXUS_PERF:" + JSON.stringify({
            "samples": frames, "elapsed_seconds": elapsed - warmup,
            "frame_ms_p95": frame_ms[p95], "process_ms_p95": process_ms[p95],
            "fps_observed": 1000.0 / (frame_ms.reduce(func(a, b): return a + b, 0.0) / frames),
            "static_memory_peak_bytes": memory_peak, "nodes_peak": nodes_peak,
            "mode": "headless_runtime", "gpu_measured": false,
            "device_measured": false, "harness_max_fps": 60, "effective_max_fps": Engine.max_fps
        }))
        quit(0)
    return false
