"""Pure read-only Godot 4 source inspection. No filesystem or external calls."""
import re

MAX_SOURCE=100_000
MAX_FINDINGS=30

def inspect_gdscript(source: str, filename: str="script.gd") -> dict:
    if len(source)>MAX_SOURCE:
        return {"error":"source_too_large","max_chars":MAX_SOURCE}
    if not filename.endswith(".gd") or "/" in filename or "\\" in filename:
        return {"error":"invalid_filename"}
    findings=[]
    rules=[
      (r"(?m)^\s*func\s+_process\s*\(", "frame_callback", "Проверь тяжёлые вычисления в _process и выделения памяти каждый кадр.", "info"),
      (r"(?m)^\s*func\s+_physics_process\s*\(", "physics_callback", "Физику обновляй в _physics_process; не смешивай с _process без необходимости.", "info"),
      (r"(?m)\bget_node\s*\(", "node_lookup", "Частые поиски узлов лучше кэшировать через @onready.", "info"),
      (r"(?m)\bload\s*\(", "sync_load", "Синхронная загрузка ресурсов во время игры может вызывать рывки.", "warning"),
      (r"(?m)\bpreload\s*\(", "preload", "Убедись, что большие ресурсы не загружаются без необходимости.", "info"),
      (r"(?m)\bqueue_redraw\s*\(", "redraw", "Проверь частоту перерисовки на мобильных устройствах.", "info"),
      (r"(?m)\bawait\s+", "async", "Проверь, что узел ещё существует после await.", "info"),
    ]
    for pattern,code,message,severity in rules:
        for match in list(re.finditer(pattern,source))[:5]:
            findings.append({"code":code,"severity":severity,"line":source.count("\n",0,match.start())+1,"message":message})
            if len(findings)>=MAX_FINDINGS:
                break
        if len(findings)>=MAX_FINDINGS:
            break
    return {"filename":filename,"lines":len(source.splitlines()),"findings":findings,
            "analysis":"static_heuristic","modified":False,"execution_enabled":False,
            "note":"Эвристики, не результат запуска Godot и не доказательство ошибки."}

def inspect_shader(source: str,filename: str="effect.gdshader") -> dict:
    if len(source)>MAX_SOURCE:
        return {"error":"source_too_large","max_chars":MAX_SOURCE}
    if not filename.endswith(".gdshader") or "/" in filename or "\\" in filename:
        return {"error":"invalid_filename"}
    findings=[]
    if "shader_type" not in source:
        findings.append({"code":"missing_shader_type","severity":"warning","message":"Не указан shader_type."})
    if re.search(r"\bdiscard\s*;",source):
        findings.append({"code":"discard","severity":"info","message":"discard может ухудшать производительность на некоторых мобильных GPU."})
    if len(re.findall(r"\btexture\s*\(",source))>5:
        findings.append({"code":"texture_samples","severity":"warning","message":"Много выборок текстур; проверь стоимость на Android GPU."})
    if re.search(r"\b(sin|cos|pow)\s*\(",source):
        findings.append({"code":"expensive_math","severity":"info","message":"Проверь сложные вычисления в fragment() на мобильных GPU."})
    return {"filename":filename,"findings":findings,"analysis":"static_heuristic",
            "modified":False,"execution_enabled":False,
            "note":"Нужны реальные GPU-профилирование и проверка рендера для оценки FPS."}
