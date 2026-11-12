"""Read-only, rules-based graphics audit for Godot 4 projects.

Recommendations are not applied to original files. No AI APIs or GPU tasks.
"""
import os
import re
from pathlib import Path
from .godot_projects import _root
from .mcp_principal import require_owner

EXCLUDE={".git",".godot",".import","node_modules","build","dist",".venv"}
MAX_FILES=1500
MAX_TEXT=100_000
ASSETS={".png",".jpg",".jpeg",".webp",".svg",".ktx",".ktx2",".glb",".gltf",".obj",".fbx"}
PROFILES={
 "low":{"max_texture_edge":1024,"particles":"few","postprocessing":"minimal"},
 "balanced":{"max_texture_edge":2048,"particles":"moderate","postprocessing":"renderer_supported"},
 "high":{"max_texture_edge":4096,"particles":"profile_first","postprocessing":"renderer_supported"},
}
EFFECTS={
 "vertex_wind":{"category":"materials","dimensions":["3d"],"renderers":["gl_compatibility","gl_compatibility","gl_compatibility"],"notes":"Вершинный ветер по высоте/маске; учитывать анимацию теней и бюджет вершин."},
 "fake_translucency":{"category":"materials","dimensions":["3d"],"renderers":["gl_compatibility"],"notes":"Упрощённое просвечивание листьев/ткани; проверить overdraw."},
 "rim_light":{"category":"materials","dimensions":["3d"],"renderers":["gl_compatibility"],"notes":"Rim light для выделения силуэта, не на каждом объекте."},
 "color_variation":{"category":"materials","dimensions":["2d","3d"],"renderers":["gl_compatibility"],"notes":"Вариация через vertex color или noise с сохранением единого стиля."},
 "emission":{"category":"materials","dimensions":["2d","3d"],"renderers":["gl_compatibility"],"notes":"Emission и светящиеся акценты; bloom зависит от рендерера."},
 "multimesh":{"category":"environment","dimensions":["2d","3d"],"renderers":["gl_compatibility"],"notes":"MultiMesh для повторяющихся объектов, только после замера."},
 "fbm_surfaces":{"category":"environment","dimensions":["3d"],"renderers":["gl_compatibility"],"notes":"FBM/noise для поверхности; ограничить число выборок на Android."},
 "water_fresnel":{"category":"environment","dimensions":["3d"],"renderers":["gl_compatibility"],"notes":"Fresnel и волновые нормали, без дорогой экранной рефракции."},
 "sky_atmosphere":{"category":"environment","dimensions":["3d"],"renderers":["gl_compatibility"],"notes":"Градиентное небо, светило, туман с учётом режима рендера."},
 "key_fill_ambient":{"category":"lighting","dimensions":["2d","3d"],"renderers":["gl_compatibility"],"notes":"Баланс основного, заполняющего и фонового света."},
 "tonemap_exposure":{"category":"lighting","dimensions":["3d"],"renderers":["gl_compatibility"],"notes":"Настроить экспозицию и tonemap только по возможностям рендера."},
 "vignette_2d":{"category":"post","dimensions":["2d"],"renderers":["gl_compatibility"],"notes":"Лёгкая виньетка canvas_item, с переключателем доступности."},
 "particles_2d":{"category":"particles","dimensions":["2d"],"renderers":["gl_compatibility"],"notes":"Дождь, пыль, снег; ограничить количество и перекрытие."},
 "particles_3d":{"category":"particles","dimensions":["3d"],"renderers":["gl_compatibility"],"notes":"GPUParticles3D, billboard, AABB и бюджет overdraw."},
}
def audit(project_id:str,profile:str="balanced")->dict:
 require_owner()
 if profile not in PROFILES:return {"error":"unknown_profile","profiles":list(PROFILES)}
 try:root=_root(project_id)
 except ValueError as exc:return {"error":str(exc),"project_id":project_id}
 settings=(root/"project.godot").read_text(errors="replace")[:MAX_TEXT]
 match=re.search(r'(?m)^renderer/rendering_method\s*=\s*"([^"]+)"',settings)
 renderer=match.group(1) if match else "unknown"
 dimension="3d" if re.search(r'(?m)\b(Node3D|MeshInstance3D|Camera3D|WorldEnvironment)\b',settings) else "2d"
 counts={"images":0,"models":0,"shaders":0,"scenes":0,"materials":0}
 flags={"particles":False,"multimesh":False,"environment":False,"water":False,"lighting":False}
 findings=[]
 examined=0
 truncated=False
 for folder,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=sorted(d for d in dirs if d not in EXCLUDE and not (Path(folder)/d).is_symlink())
  for name in sorted(files):
   p=Path(folder)/name
   if p.is_symlink() or not p.is_file():continue
   examined+=1
   if examined>MAX_FILES:
    truncated=True
    break
   suffix=p.suffix.lower()
   if suffix in ASSETS:
    counts["models" if suffix in (".glb",".gltf",".obj",".fbx") else "images"]+=1
   if suffix==".gdshader":counts["shaders"]+=1
   if suffix==".tscn":counts["scenes"]+=1
   if suffix in (".tres",".material"):counts["materials"]+=1
   if suffix not in (".tscn",".tres",".gdshader",".gd",".godot") or p.stat().st_size>MAX_TEXT:continue
   source=p.read_text(errors="replace")
   if re.search(r'\b(Node3D|MeshInstance3D|Camera3D|WorldEnvironment)\b',source):dimension="3d"
   for key,pattern in (("particles",r"GPUParticles|CPUParticles"),("multimesh",r"MultiMesh"),
                       ("environment",r"WorldEnvironment|Environment"),("water",r"water|ocean|sea"),
                       ("lighting",r"Light2D|Light3D|DirectionalLight")):
    if re.search(pattern,source,re.I):flags[key]=True
  if truncated:break
 suggestions=[]
 for key,rule in EFFECTS.items():
  if dimension not in rule["dimensions"]:continue
  suggestions.append({"effect":key,"category":rule["category"],"guidance":rule["notes"],
    "compatibility":"verify_renderer" if renderer=="unknown" else "candidate_requires_godot_validation",
    "applied":False})
 if profile=="low":suggestions=[s for s in suggestions if s["effect"] not in ("particles_3d","fbm_surfaces","multimesh")]
 if renderer=="gl_compatibility":
  findings.append({"severity":"info","code":"compatibility_renderer","message":"Compatibility: не предполагать доступность HDR glow, экранных эффектов и Forward+."})
 if renderer=="unknown":
  findings.append({"severity":"warning","code":"unknown_renderer","message":"Рендерер не определён; проверить настройки перед применением."})
 if counts["images"]>100:
  findings.append({"severity":"info","code":"texture_budget","message":"Много изображений: стоит проверить атласы, размеры текстур и видеопамять."})
 return {"project_id":project_id,"mode":"read_only","profile":profile,"dimension":dimension,
         "renderer":renderer,"scanned_files":min(examined,MAX_FILES),"truncated":truncated,
         "assets":counts,"features_detected":flags,"quality_budget":PROFILES[profile],
         "recommendations":suggestions,"findings":findings,"applied":False,
         "next_step":"Выбрать эффекты, создать изолированную копию и проверить Godot перед любыми изменениями."}

def catalog()->dict:
 require_owner()
 return {"profiles":PROFILES,"effects":EFFECTS,"automatic_apply":False,
         "external_ai_api":False,"originals_modified":False}
