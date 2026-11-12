"""Rule-only Android optimization inspection and safe Godot quality presets.

No source mutation, no performance claims without device profiling.
"""
import os
import re
from pathlib import Path
from .godot_projects import _root
from .mcp_principal import require_owner

PRESETS={
 "very_low":{"scale":0.65,"fps":30,"particles":False,"shadows":False,"effects":False},
 "low":{"scale":0.8,"fps":30,"particles":False,"shadows":False,"effects":False},
 "balanced":{"scale":1.0,"fps":45,"particles":True,"shadows":False,"effects":True},
 "high":{"scale":1.0,"fps":60,"particles":True,"shadows":True,"effects":True},
}
EXT_TEXTURE={".png",".jpg",".jpeg",".webp",".ktx",".ktx2"}
EXT_TEXT={".tscn",".tres",".gdshader",".gd"}
MAX_FILES=1800
MAX_TEXT=120_000
def inspect(project_id:str)->dict:
 require_owner()
 try:root=_root(project_id)
 except ValueError as e:return {"error":str(e)}
 issues=[]
 totals={"textures":0,"scenes":0,"scripts":0,"shaders":0,"particles":0,"lights":0,"multi_mesh":0,"large_textures":0}
 scanned=0
 for folder,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=[d for d in dirs if d not in (".git",".godot",".import","node_modules","build","dist") and not (Path(folder)/d).is_symlink()]
  for filename in files:
   path=Path(folder)/filename
   if path.is_symlink() or not path.is_file():continue
   scanned+=1
   if scanned>MAX_FILES:break
   ext=path.suffix.lower()
   if ext in EXT_TEXTURE:
    totals["textures"]+=1
    if path.stat().st_size>4_000_000:
     totals["large_textures"]+=1
     if len(issues)<60:issues.append({"path":str(path.relative_to(root)),"code":"large_texture_file","severity":"review","detail":"Файл больше 4 МБ; разрешение и GPU-сжатие не измерены."})
   if ext not in EXT_TEXT:continue
   totals[{".tscn":"scenes",".gd":"scripts",".gdshader":"shaders"}.get(ext,"scripts")]+=1
   if path.stat().st_size>MAX_TEXT:continue
   src=path.read_text(errors="replace")
   totals["particles"]+=len(re.findall(r"\b(?:GPU|CPU)Particles(?:2D|3D)\b",src))
   totals["lights"]+=len(re.findall(r"\b(?:DirectionalLight3D|OmniLight3D|SpotLight3D|PointLight2D|DirectionalLight2D)\b",src))
   totals["multi_mesh"]+=len(re.findall(r"\bMultiMesh(?:Instance2D|Instance3D)?\b",src))
   if ext==".gdshader" and re.search(r"\bSCREEN_TEXTURE\b|hint_screen_texture",src) and len(issues)<60:
    issues.append({"path":str(path.relative_to(root)),"code":"screen_texture_shader","severity":"review","detail":"Экранная текстура может быть дорогой на мобильном GPU; профилировать."})
  if scanned>MAX_FILES:break
 if totals["particles"]>20:issues.append({"code":"particle_density","severity":"review","detail":"Много узлов частиц: проверить overdraw и бюджет эмиттеров."})
 if totals["lights"]>12:issues.append({"code":"light_density","severity":"review","detail":"Много источников света: проверить динамические тени."})
 return {"project_id":project_id,"mode":"read_only","scanned_files":min(scanned,MAX_FILES),
         "truncated":scanned>MAX_FILES,"inventory":totals,"findings":issues,
         "profiles":PRESETS,"device_fps_measured":False,"device_ram_measured":False,
         "recommendations":["Профилировать на реальных слабых Android-устройствах (FPS, 1% low, память, нагрев).",
            "Добавить меню графики с сохранением пользовательского профиля.",
            "Измерить draw calls, overdraw, текстуры и стоимость частиц/теней.",
            "Тестировать стабильность после 15–30 минут игры и повторного запуска."],
         "source_modified":False}

def presets()->dict:
 require_owner()
 return {"presets":PRESETS,"device_autodetect":False,
         "dynamic_resolution":False,"manual_selection":True,
         "note":"FPS и render scale являются целевыми настройками, не измеренными результатами."}
