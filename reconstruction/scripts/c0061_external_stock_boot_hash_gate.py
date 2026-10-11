#!/usr/bin/env python3
"""Read-only external stock VBMeta boot-hash comparison; NEVER authorizes flashing."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ROOT_SHA = "d200dd45af1b30993764f38492c34c7afef7addccb844ad7642d1bd4558fd907"
EXPECTED_CI_BOOT = "c9ee726da1080d75326a0b6d8ed6cb95f6ca0870a12d384bb039131d90720252"
BOOT_IMAGE_SIZE = 71327744

def u64(buf, pos):
    return struct.unpack_from(">Q", buf, pos)[0]

def boot_descriptor(root):
    if len(root) != 8192 or root[:4] != b"AVB0":
        raise ValueError("STOCK_VBMETA_HEADER_OR_LENGTH_INVALID")
    if hashlib.sha256(root).hexdigest() != ROOT_SHA:
        raise ValueError("STOCK_VBMETA_LFS_SHA256_MISMATCH")
    auth_size, aux_size = u64(root, 12), u64(root, 20)
    descriptors_offset, descriptors_size = u64(root, 96), u64(root, 104)
    aux_start = 256 + auth_size
    if aux_start + aux_size > len(root) or descriptors_offset + descriptors_size > aux_size:
        raise ValueError("AVB_BLOCK_OUT_OF_RANGE")
    start = aux_start + descriptors_offset
    end = start + descriptors_size
    result = []
    while start < end:
        if start + 16 > end:
            raise ValueError("AVB_DESCRIPTOR_TRUNCATED")
        tag, length = u64(root, start), u64(root, start + 8)
        if start + 16 + length > end:
            raise ValueError("AVB_DESCRIPTOR_OVERFLOW")
        body = root[start + 16:start + 16 + length]
        if tag == 2:
            if len(body) < 116:
                raise ValueError("AVB_HASH_DESCRIPTOR_SHORT")
            image_size = u64(body, 0)
            algorithm = body[8:40].split(b"\0", 1)[0].decode("ascii")
            partition_size, salt_size, digest_size, flags = struct.unpack_from(">IIII", body, 40)
            if 116 + partition_size + salt_size + digest_size > len(body):
                raise ValueError("AVB_HASH_DATA_OVERFLOW")
            part = body[116:116 + partition_size].decode("ascii")
            if part == "boot":
                at = 116 + partition_size
                if algorithm != "sha256" or image_size != BOOT_IMAGE_SIZE or digest_size != 32:
                    raise ValueError("UNEXPECTED_STOCK_BOOT_DESCRIPTOR")
                result.append((image_size, body[at:at + salt_size], body[at + salt_size:at + salt_size + digest_size], flags))
        start += 16 + length
    if start != end or len(result) != 1:
        raise ValueError("BOOT_DESCRIPTOR_NOT_UNIQUE")
    return result[0]

def audit(root_file, boot_file):
    root = Path(root_file).read_bytes()
    boot = Path(boot_file).read_bytes()
    image_size, salt, signed_digest, flags = boot_descriptor(root)
    boot_sha = hashlib.sha256(boot).hexdigest()
    if boot_sha != EXPECTED_CI_BOOT:
        raise ValueError("CI_BOOT_IDENTITY_MISMATCH")
    if len(boot) < image_size:
        raise ValueError("BOOT_SHORTER_THAN_SIGNED_IMAGE_SIZE")
    digest = hashlib.sha256(salt + boot[:image_size]).digest()
    return {
        "status": "MATCH" if digest == signed_digest else "MISMATCH",
        "stock_vbmeta_sha256": ROOT_SHA,
        "ci_boot_sha256": boot_sha,
        "signed_boot_image_size": image_size,
        "boot_partition_size": len(boot),
        "descriptor_flags": flags,
        "signed_digest": signed_digest.hex(),
        "computed_digest": digest.hex(),
        "signature_root_trust_verified": False,
        "hardware_rollback_verified": False,
        "nfc_runtime_verified": False,
        "flash_authorized": False,
        "scope": "Stock signed hash-descriptor consistency only; no OEM key trust / rollback / runtime approval",
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stock-vbmeta", required=True)
    p.add_argument("--boot", required=True)
    p.add_argument("--json")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--expect-mismatch", action="store_true")
    mode.add_argument("--require-match", action="store_true")
    a = p.parse_args()
    try:
        report = audit(a.stock_vbmeta, a.boot)
    except (ValueError, OSError, struct.error, UnicodeError) as exc:
        print("C0061_EXTERNAL_AVB=BLOCKED:" + str(exc))
        return 2
    print("C0061_EXTERNAL_STOCK_BOOT_HASH=" + report["status"])
    print("C0061_OEM_ROOT_OF_TRUST=UNVERIFIED")
    print("C0061_FLASH_AUTHORIZED=NO")
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=2) + "\n")
    if a.require_match and report["status"] != "MATCH":
        return 2
    if a.expect_mismatch and report["status"] != "MISMATCH":
        return 3
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
