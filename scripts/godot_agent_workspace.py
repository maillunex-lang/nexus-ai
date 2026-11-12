"""Godot Agent safe, isolated workspace and headless verification.

CLI: python3 scripts/godot_agent_workspace.py PROJECT_ROOT WORKSPACE_PARENT
     [--patch PATCH_JSON] [--godot GODOT] [--timeout 120]
PATCH_JSON: {"path":"scripts/example.gd","expected_sha256":"...","content":"..."}
Never writes to the source project. The destination must not exist.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

EXCLUDE={".git",".godot",".import","node_modules","build","dist",".venv"}
EDITABLE={".gd",".gdshader",".tscn",".tres"}
MAX_SOURCE=512*1024*1024
MAX_FILES=12000
MAX_PATCH=100_000
MAX_LOG=12000

def safe_file(root,relative):
    if not isinstance(relative,str) or not relative or len(relative)>240 or relative.startswith("/") or "\\" in relative:
        raise ValueError("invalid_path")
    parts=relative.split("/")
    if any(part in ("",".","..") or part in EXCLUDE for part in parts):
        raise ValueError("invalid_path")
    candidate=root.joinpath(*parts)
    if candidate.suffix not in EDITABLE:
        raise ValueError("unsupported_file_type")
    cursor=root
    for part in parts:
        cursor=cursor/part
        if cursor.is_symlink():
            raise ValueError("symlink_rejected")
    if not candidate.is_file():
        raise ValueError("file_not_found")
    return candidate

def source_manifest(root):
    root=Path(root).resolve(strict=True)
    if not (root/"project.godot").is_file() or (root/"project.godot").is_symlink():
        raise ValueError("not_a_godot_project")
    files=[]
    total=0
    for folder,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in EXCLUDE and not (Path(folder)/d).is_symlink())
        for name in sorted(names):
            p=Path(folder)/name
            if p.is_symlink():
                raise ValueError("symlink_in_source")
            if not p.is_file():
                continue
            stat=p.stat()
            if not stat.st_mode & 0o400:
                raise ValueError("unreadable_source")
            total+=stat.st_size
            files.append(p)
            if len(files)>MAX_FILES or total>MAX_SOURCE:
                raise ValueError("project_exceeds_copy_limits")
    return root,files,total

def verify_patch(root,patch):
    if patch is None:
        return None
    if not isinstance(patch,dict) or set(patch)!={"path","expected_sha256","content"}:
        raise ValueError("invalid_patch")
    content=patch["content"]
    sha=patch["expected_sha256"]
    if not isinstance(content,str) or "\x00" in content or len(content.encode("utf-8"))>MAX_PATCH:
        raise ValueError("invalid_patch_content")
    if not isinstance(sha,str) or len(sha)!=64 or any(x not in "0123456789abcdef" for x in sha):
        raise ValueError("invalid_patch_sha")
    path=safe_file(root,patch["path"])
    original=path.read_bytes()
    if hashlib.sha256(original).hexdigest()!=sha:
        raise ValueError("source_changed")
    return path,content.encode("utf-8")

def run(root,parent,patch=None,godot="godot",timeout=120):
    root,files,total=source_manifest(root)
    verified=verify_patch(root,patch)
    parent=Path(parent).resolve(strict=True)
    if parent==root or parent.is_relative_to(root) or root.is_relative_to(parent):
        raise ValueError("workspace_must_be_separate")
    if parent.is_symlink():
        raise ValueError("symlink_workspace_parent")
    if not 5<=timeout<=300:
        raise ValueError("invalid_timeout")
    executable=shutil.which(godot)
    sandbox=shutil.which("bwrap")
    if not executable or not sandbox:
        raise ValueError("godot_or_bubblewrap_unavailable")
    # Each run has a fresh isolated destination, never a shared project folder.
    job_id="godot-"+uuid.uuid4().hex
    workspace=parent/job_id
    workspace.mkdir(mode=0o700)
    try:
        for source in files:
            relative=source.relative_to(root)
            destination=workspace/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,destination,follow_symlinks=False)
        if verified:
            original,content=verified
            (workspace/original.relative_to(root)).write_bytes(content)
        # Editor plugins and @tool scripts may execute code: restrict host access.
        if os.geteuid()==0:
            for folder,dirs,names in os.walk(workspace):
                os.chown(folder,65534,65534)
                for name in names:
                    os.chown(os.path.join(folder,name),65534,65534)
        executable=Path(executable).resolve(strict=True)
        command=[sandbox,"--die-with-parent","--unshare-net","--unshare-user",
                 "--uid","65534","--gid","65534",
                 "--ro-bind","/usr","/usr","--ro-bind","/lib","/lib",
                 "--ro-bind","/lib64","/lib64","--ro-bind","/bin","/bin",
                 "--ro-bind","/opt/game-tools","/opt/game-tools",
                 "--bind",str(workspace),"/workspace",
                 "--tmpfs","/tmp","--proc","/proc","--dev","/dev",
                 "--chdir","/workspace",
                 str(executable),"--headless","--path","/workspace","--editor","--quit"]
        try:
            proc=subprocess.run(command,cwd=str(workspace),capture_output=True,text=True,
                                timeout=timeout,check=False,env={"PATH":"/usr/local/bin:/usr/bin:/bin","HOME":"/workspace","XDG_CACHE_HOME":"/tmp","XDG_CONFIG_HOME":"/tmp","LANG":"C.UTF-8"})
            output=(proc.stdout+"\n"+proc.stderr)[-MAX_LOG:]
            exit_code=proc.returncode
            timed_out=False
        except subprocess.TimeoutExpired as exc:
            output=str(exc)[-MAX_LOG:]
            exit_code=None
            timed_out=True
        report={"job_id":job_id,"workspace":str(workspace),"source_project":str(root),
                "source_files":len(files),"source_bytes":total,
                "patch_applied_to_copy":bool(verified),"original_modified":False,
                "godot_exit_code":exit_code,"timed_out":timed_out,
                "passed":exit_code==0 and not timed_out,
                "godot_output":output,"timestamp":int(time.time())}
        (workspace/"nexus_godot_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
        return report
    except BaseException:
        shutil.rmtree(workspace,ignore_errors=True)
        raise

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("project_root",type=Path)
    parser.add_argument("workspace_parent",type=Path)
    parser.add_argument("--patch",type=Path)
    parser.add_argument("--godot",default="godot")
    parser.add_argument("--timeout",type=int,default=120)
    args=parser.parse_args()
    patch=json.loads(args.patch.read_text()) if args.patch else None
    print(json.dumps(run(args.project_root,args.workspace_parent,patch,args.godot,args.timeout),ensure_ascii=False))
