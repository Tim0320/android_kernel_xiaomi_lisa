#!/usr/bin/env python3
"""Read-only embedded AVB boot hash-descriptor gate (NOT bootloader AVB verification)."""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def u64(b, o):
    return struct.unpack_from(">Q", b, o)[0]


def audit(boot):
    buf = Path(boot).read_bytes()
    if len(buf) < 320 or buf[-64:-60] != b"AVBf":
        raise ValueError("AVB footer absent")
    footer = buf[-64:]
    original_size, vbmeta_offset, vbmeta_size = [u64(footer, x) for x in (12, 20, 28)]
    if not (256 <= vbmeta_size <= len(buf) - vbmeta_offset - 64):
        raise ValueError("VBMeta footer range invalid")
    vbmeta = buf[vbmeta_offset:vbmeta_offset + vbmeta_size]
    if vbmeta[:4] != b"AVB0":
        raise ValueError("VBMeta header missing")
    auth_size, aux_size = u64(vbmeta, 12), u64(vbmeta, 20)
    desc_offset, desc_size = u64(vbmeta, 96), u64(vbmeta, 104)
    aux_start = 256 + auth_size
    if aux_start + aux_size > len(vbmeta) or desc_offset + desc_size > aux_size:
        raise ValueError("VBMeta descriptor bounds invalid")
    items = vbmeta[aux_start + desc_offset:aux_start + desc_offset + desc_size]
    off = 0
    matches = []
    while off < len(items):
        if off + 16 > len(items):
            raise ValueError("truncated descriptor")
        tag, follow = u64(items, off), u64(items, off + 8)
        if off + 16 + follow > len(items):
            raise ValueError("descriptor overflow")
        body = items[off + 16:off + 16 + follow]
        if tag == 2:
            if len(body) < 116:
                raise ValueError("short hash descriptor")
            image_size = u64(body, 0)
            algo = body[8:40].split(b"\0", 1)[0].decode("ascii")
            part_len, salt_len, digest_len, flags = struct.unpack_from(">IIII", body, 40)
            stop = 116 + part_len + salt_len + digest_len
            if stop > len(body) or image_size > vbmeta_offset:
                raise ValueError("invalid hash descriptor lengths")
            partition = body[116:116 + part_len].decode("utf-8")
            salt = body[116 + part_len:116 + part_len + salt_len]
            digest = body[116 + part_len + salt_len:stop]
            h = hashlib.new(algo)
            h.update(salt)
            h.update(buf[:image_size])
            actual = h.digest()
            matches.append({"partition": partition, "image_size": image_size,
                            "algorithm": algo, "flags": flags,
                            "descriptor_digest": digest.hex(),
                            "computed_digest": actual.hex(), "match": actual == digest})
        off += 16 + follow
    if not matches or not any(d["partition"] == "boot" for d in matches):
        raise ValueError("boot hash descriptor missing")
    status = "MATCH" if all(d["match"] for d in matches) else "MISMATCH"
    return {"status": status, "partition_size": len(buf),
            "original_image_size": original_size,
            "vbmeta_offset": vbmeta_offset, "vbmeta_size": vbmeta_size,
            "vbmeta_algorithm_type": u32(vbmeta, 28),
            "descriptors": matches,
            "scope": "Embedded hash descriptor consistency only, not external vbmeta or device PASS"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=Path, required=True)
    ap.add_argument("--json", type=Path)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--require-match", action="store_true")
    group.add_argument("--expect-mismatch", action="store_true")
    args = ap.parse_args()
    result = audit(args.boot)
    print("C0061_EMBEDDED_AVB_HASH=" + result["status"])
    for d in result["descriptors"]:
        print(d["partition"] + " expected=" + d["descriptor_digest"]
              + " computed=" + d["computed_digest"])
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.require_match and result["status"] != "MATCH":
        raise SystemExit(2)
    if args.expect_mismatch and result["status"] != "MISMATCH":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
