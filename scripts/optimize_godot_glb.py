"""Standalone Blender 4.x CLI optimizer for an isolated GLB copy.

Run: blender -b --factory-startup -t 2 --python scripts/optimize_godot_glb.py -- input.glb output.glb
Only explicitly provided paths are read/written. Never modifies the source file.
"""
import bpy
import os
import sys
from pathlib import Path

def main():
    args=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    if len(args)!=2:
        raise SystemExit("Usage: -- input.glb output.glb")
    source=Path(args[0]).resolve(strict=True)
    output=Path(args[1]).resolve()
    if source.suffix.lower()!=".glb" or output.suffix.lower()!=".glb" or source==output:
        raise ValueError("Distinct .glb input and output paths required")
    if not source.is_file() or source.stat().st_size>64*1024*1024:
        raise ValueError("Input must be a GLB no larger than 64 MiB")
    if output.exists():
        raise FileExistsError("Refusing to overwrite output")
    if not output.parent.is_dir():
        raise ValueError("Output directory must already exist")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    objects=[o for o in bpy.data.objects if o.type=="MESH"]
    before=sum(len(o.data.polygons) for o in objects)
    decimated=0
    for obj in objects:
        polygons=len(obj.data.polygons)
        if polygons<=15000:
            continue
        ratio=max(0.2,min(1.0,15000/polygons))
        modifier=obj.modifiers.new("NEXUS_Mobile_Decimate","DECIMATE")
        modifier.ratio=ratio
        bpy.context.view_layer.objects.active=obj
        try:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
            decimated+=1
        except RuntimeError:
            obj.modifiers.remove(modifier)
    # Texture downscaling is performed on a copy in Blender memory.
    scaled=0
    for image in bpy.data.images:
        if image.source!="FILE" or not image.has_data:
            continue
        w,h=image.size
        if max(w,h)>2048 and min(w,h)>0:
            factor=2048/max(w,h)
            image.scale(max(1,int(w*factor)),max(1,int(h*factor)))
            scaled+=1
    bpy.ops.export_scene.gltf(filepath=str(output),export_format="GLB",
                               export_apply=True,export_image_format="AUTO")
    after=sum(len(o.data.polygons) for o in objects)
    if not output.exists() or output.stat().st_size==0:
        raise RuntimeError("No GLB produced")
    print(f"NEXUS_GLB_RESULT before_polygons={before} after_polygons={after} decimated={decimated} textures_scaled={scaled} bytes={output.stat().st_size}")

if __name__=="__main__":
    main()
