"""Allowlisted, bounded, read-only Godot source inventory. Never executes project code."""
import os
import re
import json
from pathlib import Path
from .godot_inspector import inspect_gdscript, inspect_shader

PROJECTS={"basheco":{"name":"BASHECO","root":"/projects/basheco"},
          "watermmo":{"name":"WaterMMO","root":"/projects/watermmo"},
          "agroempire":{"name":"Agro Empire Online","root":"/projects/agroempire"}}
EXTENSIONS={".tscn":"scene",".gd":"script",".gdshader":"shader",".tres":"resource"}
MAX_FILES=1200
MAX_BYTES=100_000
MAX_REPORT_FINDINGS=80
EXCLUDE={".git",".godot",".import","node_modules","build","dist",".venv"}

def _entries():
    entries=dict(PROJECTS)
    directory=Path("/registered-projects")
    if directory.is_dir():
        for folder in sorted(directory.iterdir())[:200]:
            if folder.is_symlink() or not folder.is_dir() or not re.fullmatch(r"[a-z][a-z0-9-]{2,39}",folder.name):
                continue
            manifest=folder/"manifest.json"
            if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size>4096:
                continue
            try:
                meta=json.loads(manifest.read_text())
            except (OSError,ValueError):
                continue
            if meta.get("project_id")!=folder.name or meta.get("build_enabled") is not False:
                continue
            if folder.name not in entries:
                entries[folder.name]={"name":folder.name,"root":str(folder/"source"),"inspection_only":True}
    return entries

def _root(project_id):
    if project_id not in _entries():
        raise ValueError("unknown_project")
    root=Path(_entries()[project_id]["root"])
    if root.is_symlink() or not root.is_dir() or not (root/"project.godot").is_file() or (root/"project.godot").is_symlink():
        raise ValueError("project_unavailable")
    return root

def _files(root):
    items=[]
    truncated=False
    for folder,dirs,files in os.walk(root,topdown=True,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in EXCLUDE and not (Path(folder)/d).is_symlink())
        for filename in sorted(files):
            file=Path(folder)/filename
            if file.is_symlink() or not file.is_file():
                continue
            if file.suffix not in EXTENSIONS and file.name!="project.godot":
                continue
            if len(items)>=MAX_FILES:
                truncated=True
                break
            items.append(file)
        if truncated:
            break
    return items,truncated

def _read(file,root):
    # Reject symlinks at every path component, including project root.
    if not file.is_relative_to(root):
        raise ValueError("path_outside_project")
    cursor=root
    for part in file.relative_to(root).parts:
        cursor=cursor/part
        if cursor.is_symlink():
            raise ValueError("symlink_rejected")
    with file.open("rb") as handle:
        data=handle.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:
        return None
    return data.decode("utf-8","replace")

def list_projects():
    return {"projects":[{"id":key,"name":entry["name"],"available":_available(key),"read_only":True} for key,entry in _entries().items()],"execution_enabled":False}

def _available(key):
    try:
        _root(key)
        return True
    except ValueError:
        return False

def inspect_project(project_id="basheco",include_files=False):
    try:
        root=_root(project_id)
    except ValueError as e:
        return {"error":str(e),"project_id":project_id}
    files,truncated=_files(root)
    counts={"scene":0,"script":0,"shader":0,"resource":0}
    findings=[]
    skipped=0
    project_settings={}
    scene_nodes=0
    scene_resources=0
    entries=[]
    for file in [root/"project.godot",*files]:
        rel=file.relative_to(root).as_posix()
        if file.name=="project.godot" and file!=root/"project.godot":
            continue
        if file==root/"project.godot":
            kind="project"
        else:
            kind=EXTENSIONS[file.suffix]
            counts[kind]+=1
        if include_files and len(entries)<MAX_FILES:
            entries.append({"path":rel,"kind":kind})
        try:
            source=_read(file,root)
        except (OSError,ValueError):
            skipped+=1
            continue
        if source is None:
            skipped+=1
            continue
        if kind=="project":
            for key in ("config/name","run/main_scene","renderer/rendering_method","renderer/rendering_method.mobile"):
                m=re.search(r"(?m)^\s*"+re.escape(key)+r"\s*=\s*(.+)$",source)
                if m:
                    project_settings[key]=m.group(1)[:180]
        elif kind=="scene":
            scene_nodes+=len(re.findall(r"(?m)^\[node\s",source))
            scene_resources+=len(re.findall(r"(?m)^\[(?:ext_resource|sub_resource)\s",source))
            if not re.search(r"(?m)^\[gd_scene\b",source):
                findings.append({"path":rel,"code":"scene_header_missing","severity":"warning","message":"Не найден заголовок gd_scene."})
        elif kind in ("script","shader"):
            result=inspect_gdscript(source,file.name) if kind=="script" else inspect_shader(source,file.name)
            for issue in result.get("findings",[]):
                if len(findings)<MAX_REPORT_FINDINGS:
                    findings.append({"path":rel,**issue})
    return {"project_id":project_id,"name":_entries()[project_id]["name"],
            "settings":project_settings,"counts":counts,"scene_nodes":scene_nodes,
            "scene_resources":scene_resources,"findings":findings[:MAX_REPORT_FINDINGS],
            "findings_truncated":len(findings)>=MAX_REPORT_FINDINGS,
            "files_truncated":truncated,"skipped_large_or_unreadable":skipped,
            "files":entries if include_files else [],
            "analysis":"static_heuristic","read_only":True,"execution_enabled":False,
            "note":"Не запускает Godot, не проверяет FPS и не изменяет файлы."}

def inspect_file(project_id,relative_path):
    try:
        root=_root(project_id)
    except ValueError as e:
        return {"error":str(e)}
    if not isinstance(relative_path,str) or len(relative_path)>240 or relative_path.startswith("/") or "\\" in relative_path:
        return {"error":"invalid_path"}
    parts=relative_path.split("/")
    if any(part in ("",".","..") or part in EXCLUDE for part in parts):
        return {"error":"invalid_path"}
    path=root.joinpath(*parts)
    if path.suffix not in EXTENSIONS and path.name!="project.godot":
        return {"error":"unsupported_file_type"}
    if not path.is_file():
        return {"error":"not_found"}
    try:
        source=_read(path,root)
    except (ValueError,OSError):
        return {"error":"unreadable_or_symlink"}
    if source is None:
        return {"error":"file_too_large"}
    kind=EXTENSIONS.get(path.suffix,"project")
    if kind=="script":
        analysis=inspect_gdscript(source,path.name)
    elif kind=="shader":
        analysis=inspect_shader(source,path.name)
    else:
        analysis={"sections":re.findall(r"(?m)^\[([^\]\r\n]{1,150})\]",source)[:120],
                  "lines":len(source.splitlines()),"analysis":"static_structure"}
    return {"project_id":project_id,"path":relative_path,"kind":kind,
            "source_sha256":__import__("hashlib").sha256(source.encode("utf-8")).hexdigest(),
            "analysis":analysis,"read_only":True,"execution_enabled":False}
