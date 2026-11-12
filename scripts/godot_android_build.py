"""Build unsigned/standard-debug Android APK from a previously validated workspace.

No release signing, no upload, no original project modifications.
Only host-controlled Godot workspaces with passing validation reports are accepted.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path("/opt/nexus-ai/godot-workspaces")
ID=re.compile(r"godot-[0-9a-f]{32}\Z")
MAX_APK=250*1024*1024

def build(job_id,timeout=240):
    if not ID.fullmatch(job_id):
        raise ValueError("invalid_job_id")
    workspace=ROOT/job_id
    report_file=workspace/"nexus_godot_report.json"
    if workspace.is_symlink() or report_file.is_symlink() or not report_file.is_file():
        raise ValueError("workspace_unavailable")
    report=json.loads(report_file.read_text())
    if report.get("job_id")!=job_id or report.get("passed") is not True:
        raise ValueError("validation_not_passed")
    preset=workspace/"export_presets.cfg"
    if preset.is_symlink() or not preset.is_file():
        raise ValueError("android_preset_unavailable")
    contents=preset.read_text()
    if 'platform="Android"' not in contents or 'name="Android"' not in contents:
        raise ValueError("android_preset_unavailable")
    # A release key must never be mounted or requested.
    if not 30<=timeout<=300:
        raise ValueError("invalid_timeout")
    executable=Path("/opt/game-tools/godot/4.7.2-stable/Godot_v4.7.2-stable_linux.x86_64")
    if not executable.is_file():
        raise ValueError("approved_godot_binary_unavailable")
    bwrap=shutil.which("bwrap")
    if not bwrap:
        raise ValueError("sandbox_unavailable")
    templates=Path("/root/.local/share/godot/export_templates")
    if not templates.is_dir():
        raise ValueError("export_templates_unavailable")
    out=workspace/"nexus-build"
    out.mkdir(exist_ok=True)
    apk=out/"android-debug.apk"
    home=out/"home"
    (home/".local/share/godot/export_templates").mkdir(parents=True,exist_ok=True)
    (home/".config/godot").mkdir(parents=True,exist_ok=True)
    (home/".cache").mkdir(exist_ok=True)
    (home/".config/godot/editor_settings-4.7.tres").write_text('[gd_resource type="EditorSettings" format=3]\\n[resource]\\nexport/android/android_sdk_path = "/opt/android-sdk"\\nexport/android/java_sdk_path = "/usr/lib/jvm/java-17-openjdk-amd64"\\n')
    if apk.exists():
        raise ValueError("artifact_already_exists")
    # Bind only the validated workspace, SDK and export templates. Never bind
    # release signing keys, host HOME, credentials, other games or host network.
    command=[bwrap,"--die-with-parent","--unshare-net","--unshare-pid","--unshare-user",
             "--uid","0","--gid","0",
             "--ro-bind","/usr","/usr","--ro-bind","/lib","/lib",
             "--ro-bind","/lib64","/lib64","--ro-bind","/bin","/bin",
             "--ro-bind","/opt/game-tools","/opt/game-tools",
             "--ro-bind","/opt/android-sdk","/opt/android-sdk",
             "--ro-bind",str(templates),"/home/nexus/.local/share/godot/export_templates",
             "--bind",str(workspace),"/workspace",
             "--tmpfs","/tmp","--dir","/home","--bind",str(home),"/home/nexus",
             "--proc","/proc","--dev","/dev","--chdir","/workspace",
             str(executable),"--headless","--path","/workspace",
             "--export-debug","Android","/workspace/nexus-build/android-debug.apk"]
    try:
        p=subprocess.run(command,capture_output=True,text=True,timeout=timeout,
                         env={"PATH":"/usr/local/bin:/usr/bin:/bin","HOME":"/home/nexus",
                              "ANDROID_HOME":"/opt/android-sdk","ANDROID_SDK_ROOT":"/opt/android-sdk",
                              "JAVA_HOME":"/usr/lib/jvm/default-java","LANG":"C.UTF-8"})
        log=(p.stdout+"\n"+p.stderr)[-9000:]
        timed_out=False
        code=p.returncode
    except subprocess.TimeoutExpired as exc:
        log=str(exc)[-9000:]
        timed_out=True
        code=None
    success=code==0 and apk.is_file() and 0<apk.stat().st_size<=MAX_APK
    result={"validation_job_id":job_id,"passed":success,"exit_code":code,
            "timed_out":timed_out,"artifact":str(apk) if success else None,
            "bytes":apk.stat().st_size if success else None,
            "sha256":hashlib.sha256(apk.read_bytes()).hexdigest() if success else None,
            "log":log,"original_modified":False,"published":False}
    (out/"build_report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=="__main__":
    result=build(sys.argv[1])
    print(json.dumps(result,ensure_ascii=False))
    sys.exit(0 if result["passed"] else 1)
