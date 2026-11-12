"""Read-only Godot source change previews pinned to exact source SHA-256.

No writes to mounted project, no Godot execution, no arbitrary paths.
"""
import difflib
import hashlib
from .godot_projects import _root,_read,EXCLUDE,EXTENSIONS,MAX_BYTES
from .godot_inspector import inspect_gdscript,inspect_shader

EDITABLE={".gd",".gdshader",".tscn",".tres"}
MAX_DIFF=18000

def preview(project_id:str,relative_path:str,expected_sha256:str,new_source:str)->dict:
    if not isinstance(relative_path,str) or len(relative_path)>240 or relative_path.startswith("/") or "\\" in relative_path:
        return {"error":"invalid_path"}
    parts=relative_path.split("/")
    if any(x in ("",".","..") or x in EXCLUDE for x in parts):
        return {"error":"invalid_path"}
    if not isinstance(new_source,str) or len(new_source.encode("utf-8"))>MAX_BYTES or "\x00" in new_source:
        return {"error":"invalid_content"}
    if not isinstance(expected_sha256,str) or len(expected_sha256)!=64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        return {"error":"invalid_sha256"}
    try:
        root=_root(project_id)
    except ValueError as exc:
        return {"error":str(exc)}
    path=root.joinpath(*parts)
    if path.suffix not in EDITABLE:
        return {"error":"unsupported_file_type"}
    if not path.is_file():
        return {"error":"not_found"}
    try:
        old=_read(path,root)
    except (ValueError,OSError):
        return {"error":"unreadable_or_symlink"}
    if old is None:
        return {"error":"file_too_large"}
    old_sha=hashlib.sha256(old.encode("utf-8")).hexdigest()
    if old_sha!=expected_sha256:
        return {"error":"source_changed","current_sha256":old_sha}
    if path.suffix==".gd":
        findings=inspect_gdscript(new_source,path.name).get("findings",[])
    elif path.suffix==".gdshader":
        findings=inspect_shader(new_source,path.name).get("findings",[])
    else:
        prefix="[gd_scene" if path.suffix==".tscn" else "[gd_resource"
        findings=[] if new_source.lstrip().startswith(prefix) else [{"code":"missing_resource_header","severity":"warning"}]
    delta="".join(difflib.unified_diff(old.splitlines(keepends=True),new_source.splitlines(keepends=True),
                                      fromfile="current/"+relative_path,tofile="proposed/"+relative_path))
    return {"project_id":project_id,"path":relative_path,"source_sha256":old_sha,
            "proposed_sha256":hashlib.sha256(new_source.encode("utf-8")).hexdigest(),
            "diff":delta[:MAX_DIFF],"diff_truncated":len(delta)>MAX_DIFF,
            "findings":findings[:80],"changed":old!=new_source,
            "read_only":True,"applied":False,"godot_executed":False}
