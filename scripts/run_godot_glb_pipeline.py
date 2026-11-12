"""Offline, bounded GLB optimization runner. No Meshy API calls or project mutations.

Usage: python scripts/run_godot_glb_pipeline.py input.glb output.glb
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from nexus.glb_binary import inspect_glb

def run(source:Path,target:Path,blender="blender"):
    source=source.resolve(strict=True)
    target=target.resolve()
    if source==target or source.suffix.lower()!=".glb" or target.suffix.lower()!=".glb":
        raise ValueError("Source and output must be different GLB files")
    if target.exists() or not target.parent.is_dir():
        raise ValueError("Output must not exist; directory must exist")
    if source.stat().st_size>64*1024*1024:
        raise ValueError("GLB exceeds 64 MiB")
    before=inspect_glb(source.read_bytes())
    if "error" in before:
        raise ValueError("Invalid source GLB: "+before["error"])
    exe=shutil.which(blender)
    if not exe:
        raise RuntimeError("Blender executable unavailable")
    command=[exe,"-b","--factory-startup","-t","2","--python",
             str(ROOT/"scripts/optimize_godot_glb.py"),"--",str(source),str(target)]
    try:
        proc=subprocess.run(command,capture_output=True,text=True,timeout=180,
                            check=False,env={**os.environ,"BLENDER_USER_CONFIG":"/tmp/nexus-blender-config"})
    except subprocess.TimeoutExpired:
        target.unlink(missing_ok=True)
        raise RuntimeError("Blender timed out") from None
    if proc.returncode or not target.is_file() or target.stat().st_size>64*1024*1024:
        target.unlink(missing_ok=True)
        raise RuntimeError("Blender failed or output exceeded size limit")
    after=inspect_glb(target.read_bytes())
    if "error" in after:
        target.unlink(missing_ok=True)
        raise RuntimeError("Blender output failed GLB validation")
    return {"input":str(source),"output":str(target),
            "before":before,"after":after,"optimized":True,
            "source_preserved":True,"paid_credits_spent":0}

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("input",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    print(json.dumps(run(args.input,args.output),ensure_ascii=False))
