import json,struct
from nexus.glb_binary import inspect_glb

def glb(doc):
    payload=json.dumps(doc).encode()
    payload+=b" " * ((-len(payload))%4)
    return struct.pack("<4sII",b"glTF",2,20+len(payload))+struct.pack("<I4s",len(payload),b"JSON")+payload

def test_glb_triangle_count():
    data=glb({"asset":{"version":"2.0"},"accessors":[{"count":300}],
        "meshes":[{"primitives":[{"indices":0}]}]})
    result=inspect_glb(data)
    assert result["estimated_triangles"]==100
    assert result["geometry_verified"] is True
    assert result["optimized"] is False

def test_glb_invalid_header_and_length():
    data=glb({"asset":{"version":"2.0"}})
    assert inspect_glb(b"bad"+data[3:])["error"]=="invalid_glb_header"
    assert inspect_glb(data[:-1])["error"]=="invalid_glb_header"

def test_glb_large_file_rejected():
    assert inspect_glb(b"X"*(64*1024*1024+1))["error"]=="invalid_glb_size"

def test_glb_unmeasured_primitive():
    data=glb({"asset":{"version":"2.0"},"meshes":[{"primitives":[{"mode":1}]}]})
    result=inspect_glb(data)
    assert result["unmeasured_primitives"]==1
    assert result["geometry_verified"] is False
