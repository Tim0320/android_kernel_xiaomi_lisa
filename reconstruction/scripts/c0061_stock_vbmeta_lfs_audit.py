#!/usr/bin/env python3
"""Read-only stock AVB header provenance; does not verify OEM signatures."""
import hashlib
import json
import pathlib
import struct
import sys

EXPECTED = {
 "vbmeta.img": (8192, "d200dd45af1b30993764f38492c34c7afef7addccb844ad7642d1bd4558fd907"),
 "vbmeta_system.img": (4096, "ea61d50a1cddf84444a6bd89fbcf9c84360d4cacfb6664271ddaa23c502a2420"),
}
def u32(x, off): return struct.unpack_from(">I", x, off)[0]
def u64(x, off): return struct.unpack_from(">Q", x, off)[0]
def inspect(path):
    raw = pathlib.Path(path).read_bytes()
    expected_size, digest = EXPECT[pathlib.Path(path).name]
    if len(raw) != expected_size or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("LFS_PAYLOAD_HASH_OR_SIZE_MISMATCH")
    if raw[:4] != b"AVB0" or len(raw) < 256:
        raise ValueError("INVALID_AVB_HEADER")
    auth, aux = u64(raw, 12), u64(raw, 20)
    if 256 + auth + aux > len(raw):
        raise ValueError("AVB_BLOCK_OUT_OF_RANGE")
    desc_off, desc_size = u64(raw, 96), u64(raw, 104)
    if desc_off + desc_size > aux:
        raise ValueError("AVB_DESCRIPTOR_OUT_OF_RANGE")
    descriptor_types = []
    pos = 256 + auth + desc_off
    end = pos + desc_size
    while pos < end:
        if pos + 16 > end: raise ValueError("AVB_DESCRIPTOR_TRUNCATED")
        tag, size = u64(raw, pos), u64(raw, pos + 8)
        if pos + 16 + size > end: raise ValueError("AVB_DESCRIPTOR_OVERFLOW")
        descriptor_types.append({"tag": tag, "size": size})
        pos += 16 + size
    return {"image": pathlib.Path(path).name,"sha256": digest,
        "algorithm_type":u32(raw,28),"rollback_index":u64(raw,112),
        "flags":u32(raw,120),"rollback_index_location":u32(raw,124),
        "descriptor_types":descriptor_types,
        "signature_verified":False,"device_rollback_verified":False,
        "flash_authorized":False}
if __name__=="__main__":
    output=[]
    for item in sys.argv[1:]:
        output.append(inspect(item))
    print(json.dumps(output,indent=2))
