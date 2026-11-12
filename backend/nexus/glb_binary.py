"""Bounded binary GLB 2.0 inspection, including mesh triangle estimates.

No external resources are fetched and no untrusted model code is executed.
"""
import json
import struct
from .godot_glb_audit import assess_gltf

MAX_FILE=64*1024*1024
MAX_JSON=8*1024*1024

def inspect_glb(data: bytes) -> dict:
    if not isinstance(data,bytes) or len(data)<20 or len(data)>MAX_FILE:
        return {"error":"invalid_glb_size"}
    magic,version,total=struct.unpack_from("<4sII",data)
    if magic!=b"glTF" or version!=2 or total!=len(data):
        return {"error":"invalid_glb_header"}
    offset=12
    chunks=[]
    while offset<len(data):
        if offset+8>len(data):
            return {"error":"invalid_chunk_header"}
        length,kind=struct.unpack_from("<I4s",data,offset)
        offset+=8
        if length%4 or length>len(data)-offset:
            return {"error":"invalid_chunk_length"}
        chunks.append((kind,offset,length))
        offset+=length
        if len(chunks)>2:
            return {"error":"too_many_chunks"}
    if not chunks or chunks[0][0]!=b"JSON" or chunks[0][2]>MAX_JSON:
        return {"error":"missing_json_chunk"}
    if len(chunks)==2 and chunks[1][0]!=b"BIN\\x00".decode("unicode_escape").encode("latin1"):
        return {"error":"invalid_bin_chunk"}
    try:
        doc=json.loads(data[chunks[0][1]:chunks[0][1]+chunks[0][2]].decode("utf-8"))
    except (UnicodeError,ValueError):
        return {"error":"invalid_json"}
    report=assess_gltf(doc)
    if "error" in report:
        return report
    accessors=doc.get("accessors",[])
    if not isinstance(accessors,list):
        return {"error":"invalid_accessors"}
    triangles=0
    unsupported=0
    for mesh in doc.get("meshes",[]):
        if not isinstance(mesh,dict) or not isinstance(mesh.get("primitives",[]),list):
            return {"error":"invalid_mesh"}
        for primitive in mesh.get("primitives",[]):
            if not isinstance(primitive,dict):
                return {"error":"invalid_primitive"}
            mode=primitive.get("mode",4)
            index=primitive.get("indices")
            if index is None:
                position=primitive.get("attributes",{}).get("POSITION")
                index=position
            if not isinstance(index,int) or isinstance(index,bool) or not 0<=index<len(accessors):
                unsupported+=1
                continue
            count=accessors[index].get("count") if isinstance(accessors[index],dict) else None
            if not isinstance(count,int) or count<0:
                unsupported+=1
                continue
            if mode==4:
                triangles+=count//3
            elif mode in (5,6):
                triangles+=max(0,count-2)
            else:
                unsupported+=1
    report.update({"estimated_triangles":triangles,"unmeasured_primitives":unsupported,
                   "geometry_verified":unsupported==0,
                   "binary_bytes":len(data)})
    if triangles>120_000:
        report["warnings"].append("high_triangle_count_for_mobile")
    return report
