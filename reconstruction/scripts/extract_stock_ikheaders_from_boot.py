#!/usr/bin/env python3
"""Extract exact embedded IKHEADERS from the pinned Lisa stock boot image.

Artifact-independent by design: validate the known stock boot, extract its raw
ARM64 Image, locate the embedded XZ tar stream by content, and materialize the
headers used by QGKI/genksyms compatibility gates.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import lzma
import struct
import tarfile
from pathlib import Path

EXPECTED_BOOT_SHA256 = "e6f8c978c2cf0a9473d0ac73cdcf3ffb14747246fdc47f82245c43221eb4cbf1"
EXPECTED_BOOT_BYTES = 201326592
EXPECTED_KERNEL_BYTES = 51436032
XZ_MAGIC = b"\xfd7zXZ\x00"
REQUIRED = {
    "include/linux/kconfig.h",
    "include/linux/power_debug.h",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_kernel(boot: bytes) -> bytes:
    if boot[:8] != b"ANDROID!":
        raise RuntimeError("stock input is not an Android boot image")
    kernel_size = struct.unpack_from("<I", boot, 8)[0]
    header_version = struct.unpack_from("<I", boot, 40)[0]
    page_size = 4096 if header_version >= 3 else struct.unpack_from("<I", boot, 36)[0]
    if kernel_size != EXPECTED_KERNEL_BYTES:
        raise RuntimeError(f"unexpected stock kernel size: {kernel_size}")
    image = boot[page_size:page_size + kernel_size]
    if len(image) != kernel_size:
        raise RuntimeError("truncated stock kernel payload")
    if struct.unpack_from("<I", image, 0x38)[0] != 0x644D5241:
        raise RuntimeError("stock kernel payload is not an ARM64 Image")
    return image


def find_ikheaders(image: bytes) -> tuple[int, int, bytes, list[str]]:
    start = 0
    attempts = 0
    while True:
        offset = image.find(XZ_MAGIC, start)
        if offset < 0:
            break
        attempts += 1
        dec = lzma.LZMADecompressor(format=lzma.FORMAT_XZ)
        try:
            payload = dec.decompress(image[offset:], max_length=256 * 1024 * 1024)
        except lzma.LZMAError:
            start = offset + 1
            continue
        if not dec.eof:
            start = offset + 1
            continue
        consumed = len(image[offset:]) - len(dec.unused_data)
        try:
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as tf:
                names = tf.getnames()
        except tarfile.TarError:
            start = offset + 1
            continue
        normalized = {name.lstrip("./") for name in names}
        if REQUIRED.issubset(normalized):
            return offset, consumed, payload, sorted(normalized)
        start = offset + 1
    raise RuntimeError(f"embedded IKHEADERS tar.xz not found after {attempts} XZ candidates")


def safe_extract(payload: bytes, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    root = out.resolve()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as tf:
        for member in tf.getmembers():
            target = (out / member.name).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError(f"unsafe IKHEADERS path: {member.name}")
        tf.extractall(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--manifest", type=Path, default=Path("stock-ikheaders-extract.json"))
    args = ap.parse_args()

    boot = args.boot.read_bytes()
    boot_hash = sha256(boot)
    if len(boot) != EXPECTED_BOOT_BYTES:
        raise RuntimeError(f"unexpected stock boot size: {len(boot)}")
    if boot_hash != EXPECTED_BOOT_SHA256:
        raise RuntimeError(f"unexpected stock boot sha256: {boot_hash}")

    image = extract_kernel(boot)
    offset, compressed_bytes, payload, names = find_ikheaders(image)
    safe_extract(payload, args.out)

    for rel in REQUIRED:
        path = args.out / rel
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"required stock header missing after extraction: {rel}")

    manifest = {
        "boot_sha256": boot_hash,
        "boot_bytes": len(boot),
        "kernel_sha256": sha256(image),
        "kernel_bytes": len(image),
        "ikheaders_offset": offset,
        "ikheaders_compressed_bytes": compressed_bytes,
        "ikheaders_tar_bytes": len(payload),
        "file_count": len(names),
        "required": sorted(REQUIRED),
    }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, sort_keys=True))
    print("LISA_STOCK_IKHEADERS_EXTRACT=PASS")


if __name__ == "__main__":
    main()
