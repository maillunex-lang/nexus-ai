"""Static Godot 4 Android suitability assessment from glTF 2.0 JSON metadata.

Never runs Blender, imports untrusted assets or claims optimization was performed.
"""
from typing import Any

MAX_NODES=5000
MAX_TRIANGLES=120_000
MAX_TEXTURES=32
MAX_TEXTURE_DIMENSION=2048

def assess_gltf(document: dict[str,Any]) -> dict:
    if not isinstance(document,dict) or not isinstance(document.get("asset"),dict) or not str(
            document["asset"].get("version","")).startswith("2."):
        return {"error":"invalid_gltf_2"}
    meshes=document.get("meshes",[])
    nodes=document.get("nodes",[])
    textures=document.get("textures",[])
    images=document.get("images",[])
    materials=document.get("materials",[])
    if not all(isinstance(v,list) for v in (meshes,nodes,textures,images,materials)):
        return {"error":"invalid_collections"}
    warnings=[]
    if len(nodes)>MAX_NODES:
        warnings.append("excessive_nodes")
    if len(textures)>MAX_TEXTURES:
        warnings.append("excessive_textures")
    if len(materials)>64:
        warnings.append("excessive_materials")
    if document.get("extensionsRequired"):
        warnings.append("check_godot_extension_compatibility")
    primitives=sum(len(m.get("primitives",[])) for m in meshes if isinstance(m,dict))
    if primitives>256:
        warnings.append("excessive_mesh_primitives")
    for image in images:
        if isinstance(image,dict) and image.get("mimeType") not in (None,"image/png","image/jpeg","image/webp","image/ktx2"):
            warnings.append("unsupported_texture_format")
            break
    return {"target":"Godot 4 Android","mesh_count":len(meshes),"node_count":len(nodes),
            "primitive_count":primitives,"material_count":len(materials),
            "texture_count":len(textures),"warnings":warnings,
            "recommendations":["Use mobile-friendly texture resolution (usually <=2048px)",
               "Prefer few draw calls and materials","Generate LODs and verify triangle counts in Blender",
               "Test Vulkan Mobile and Compatibility renderers on target Android devices"],
            "geometry_verified":False,"optimized":False,
            "note":"Metadata-only audit; polygon counts and texture dimensions require binary inspection."}
