"""Host-only source intake. No project execution, no automatic build permission."""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

BASE=Path("/opt/nexus-ai/godot-queue")
ROOT=Path("/opt/nexus-ai/registered-projects")
ID=re.compile(r"[a-z][a-z0-9-]{2,39}\Z")
JOB=re.compile(r"onboard-[0-9a-f]{32}\Z")
MAX_FILES=3000
MAX_TOTAL=250*1024*1024
EXCLUDE={".git",".godot",".import","node_modules",".venv","build","dist","nexus-build"}
HOST_ROOTS=(Path("/opt"),Path("/home/gamedev/projects"))

def check_tree(source):
    total=0
    count=0
    for folder,dirs,files in os.walk(source,followlinks=False):
        dirs[:]=[d for d in dirs if d not in EXCLUDE]
        for name in [*dirs,*files]:
            path=Path(folder)/name
            if path.is_symlink():
                raise ValueError("symlink_not_allowed")
        for name in files:
            path=Path(folder)/name
            if name.startswith(".env") or name.endswith((".key",".pem",".p12",".keystore")):
                raise ValueError("secret_like_file_detected")
            count+=1
            total+=path.stat().st_size
            if count>MAX_FILES or total>MAX_TOTAL:
                raise ValueError("project_size_limit")
    if not (source/"project.godot").is_file():
        raise ValueError("godot_project_missing")
    return {"files":count,"bytes":total}

def process(file):
    job=file.stem
    if not JOB.fullmatch(job) or file.is_symlink() or file.stat().st_size>4096:
        return
    running=BASE/"onboard_running"/file.name
    file.rename(running)
    data={}
    stage=None
    try:
        data=json.loads(running.read_text())
        if set(data)!={"job_id","project_id","source_type","source","requested_by"} or data["job_id"]!=job:
            raise ValueError("invalid_request")
        pid=data["project_id"]
        if not isinstance(pid,str) or not ID.fullmatch(pid):
            raise ValueError("invalid_project_id")
        ROOT.mkdir(parents=True,exist_ok=True)
        dest=ROOT/pid
        if dest.exists() or dest.is_symlink():
            raise ValueError("project_id_already_registered")
        stage=Path(tempfile.mkdtemp(prefix="onboard-",dir=ROOT))
        source=data["source"]
        if data["source_type"]=="wizard":
            from godot_game_wizard import generate
            generate(stage/"source",json.loads(source))
            metadata=check_tree(stage/"source")
        elif data["source_type"]=="template":
            if not isinstance(source,str) or not 1<=len(source)<=70 or any(ord(c)<32 or c in '\\\\/<>"' for c in source):
                raise ValueError("invalid_project_title")
            folder=stage/"source"
            folder.mkdir()
            title=source.replace('"',"'")
            (folder/"project.godot").write_text(
                'config_version=5\\n\\n[application]\\nconfig/name="'+title+
                '"\\nrun/main_scene="res://scenes/main.tscn"\\n\\n[rendering]\\nrenderer/rendering_method="gl_compatibility"\\n'
            )
            (folder/"scenes").mkdir()
            (folder/"scripts").mkdir()
            (folder/"scenes"/"main.tscn").write_text(
                '[gd_scene load_steps=2 format=3]\\n\\n[ext_resource type="Script" path="res://scripts/main.gd" id="1"]\\n\\n[node name="Main" type="Node2D"]\\nscript = ExtResource("1")\\n'
            )
            (folder/"scripts"/"main.gd").write_text('extends Node2D\\n\\nfunc _ready() -> void:\\n\\tpass\\n')
            metadata=check_tree(folder)
        elif data["source_type"]=="lunex":
            if not isinstance(source,str) or ".." in Path(source).parts:
                raise ValueError("invalid_source")
            path=Path(source)
            if path.is_symlink() or not path.is_dir():
                raise ValueError("source_unavailable")
            resolved=path.resolve(strict=True)
            if not any(resolved.is_relative_to(root) for root in HOST_ROOTS) or resolved.is_relative_to(Path("/opt/nexus-ai")):
                raise ValueError("source_not_permitted")
            metadata=check_tree(resolved)
            shutil.copytree(resolved,stage/"source",symlinks=True,
                            ignore=shutil.ignore_patterns(*EXCLUDE))
        elif data["source_type"]=="github":
            if not isinstance(source,str) or not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git",source):
                raise ValueError("invalid_github_url")
            env={"PATH":"/usr/bin:/bin","HOME":str(stage),"GIT_CONFIG_NOSYSTEM":"1",
                 "GIT_TERMINAL_PROMPT":"0","GIT_LFS_SKIP_SMUDGE":"1",
                 "GIT_CONFIG_COUNT":"2","GIT_CONFIG_KEY_0":"protocol.file.allow",
                 "GIT_CONFIG_VALUE_0":"never","GIT_CONFIG_KEY_1":"protocol.ext.allow",
                 "GIT_CONFIG_VALUE_1":"never"}
            subprocess.run(["/usr/bin/git","-c","credential.helper=","clone","--depth","1",
                            "--single-branch","--no-tags","--",source,str(stage/"source")],
                           env=env,capture_output=True,text=True,timeout=90,check=True)
            metadata=check_tree(stage/"source")
            shutil.rmtree(stage/"source"/".git",ignore_errors=True)
        else:
            raise ValueError("unsupported_source")
        (stage/"manifest.json").write_text(json.dumps({"project_id":pid,"source_type":data["source_type"],
            "source":source,"requested_by":data["requested_by"],"build_enabled":False,
            "inspection_only":True,**metadata},ensure_ascii=False))
        stage.rename(dest)
        stage=None
        state="onboard_completed"
        result={"registered":True,"project_id":pid,"files":metadata["files"],
                "bytes":metadata["bytes"],"build_enabled":False,"inspection_only":True}
    except Exception as exc:
        state="onboard_failed"
        result={"registered":False,"error":type(exc).__name__+":"+str(exc)[:180]}
    finally:
        if stage is not None:
            shutil.rmtree(stage,ignore_errors=True)
    with (BASE/state/file.name).open("x") as out:
        json.dump({"job_id":job,"requested_by":data.get("requested_by"),"result":result},out)
    running.unlink()

def main():
    for state in ("onboard_pending","onboard_running","onboard_completed","onboard_failed"):
        (BASE/state).mkdir(parents=True,exist_ok=True)
    for file in sorted((BASE/"onboard_pending").glob("onboard-*.json"))[:1]:
        process(file)

if __name__=="__main__":
    main()
