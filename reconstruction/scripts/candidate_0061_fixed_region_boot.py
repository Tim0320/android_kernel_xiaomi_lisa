#!/usr/bin/env python3
"""Candidate0061 fixed-region boot repack.

Match the verified Candidate0046 -> Candidate0059 packaging contract:
- keep the stock Android boot v3 header page byte-for-byte;
- keep the stock 51,436,032-byte kernel region size in the header;
- place the rebuilt Image at the start of that region and zero-pad the rest;
- do not move the stock ramdisk;
- preserve every byte after the fixed kernel region, including AVB0 metadata
  and the AVBf footer.

This intentionally rejects the earlier C0061 dynamic repack that changed the
kernel_size header, moved the ramdisk, and zeroed the AVB tail.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

PAGE = 4096


def align(v: int, a: int) -> int:
    return (v + a - 1) // a * a


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", type=Path, required=True)
    ap.add_argument("--kernel", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--validation", type=Path, required=True)
    ap.add_argument("--target-release", required=True)
    ap.add_argument("--expected-stock-sha", required=True)
    ap.add_argument("--expected-partition-size", type=int, default=201326592)
    ap.add_argument("--expected-stock-kernel-size", type=int, default=51436032)
    ap.add_argument("--expected-stock-ramdisk-size", type=int, default=19883180)
    ap.add_argument("--expected-stock-ramdisk-sha",
                    default="0dc218f3167e560444634a6a8cf969eb4470bcf452837a3e23bf45ea0a6819ae")
    ap.add_argument("--expected-kernel-sha")
    args = ap.parse_args()

    stock = args.stock.read_bytes()
    kernel = args.kernel.read_bytes()
    target = args.target_release.encode()

    if sha(stock) != args.expected_stock_sha:
        raise SystemExit("stock boot SHA mismatch")
    if len(stock) != args.expected_partition_size:
        raise SystemExit("stock boot partition size mismatch")
    if stock[:8] != b"ANDROID!":
        raise SystemExit("stock Android boot magic missing")
    if struct.unpack_from("<I", stock, 40)[0] != 3:
        raise SystemExit("stock boot is not Android header v3")

    stock_kernel_size = struct.unpack_from("<I", stock, 8)[0]
    ramdisk_size = struct.unpack_from("<I", stock, 12)[0]
    if stock_kernel_size != args.expected_stock_kernel_size:
        raise SystemExit(f"stock kernel region {stock_kernel_size} != {args.expected_stock_kernel_size}")
    if ramdisk_size != args.expected_stock_ramdisk_size:
        raise SystemExit(f"stock ramdisk size {ramdisk_size} != {args.expected_stock_ramdisk_size}")
    if len(kernel) > stock_kernel_size:
        raise SystemExit("Candidate0061 Image exceeds verified stock kernel region")
    if len(kernel) < 0x3c or struct.unpack_from("<I", kernel, 0x38)[0] != 0x644D5241:
        raise SystemExit("Candidate0061 ARM64 Image magic missing")
    if target not in kernel:
        raise SystemExit("Candidate0061 target release missing from Image")
    if args.expected_kernel_sha and sha(kernel) != args.expected_kernel_sha:
        raise SystemExit("Candidate0061 Image SHA mismatch")

    ramdisk_off = align(PAGE + stock_kernel_size, PAGE)
    ramdisk = stock[ramdisk_off:ramdisk_off + ramdisk_size]
    if len(ramdisk) != ramdisk_size:
        raise SystemExit("stock ramdisk truncated")
    if sha(ramdisk) != args.expected_stock_ramdisk_sha:
        raise SystemExit("stock ramdisk SHA mismatch")
    logical_end = align(ramdisk_off + ramdisk_size, PAGE)
    if stock[logical_end:logical_end + 4] != b"AVB0":
        raise SystemExit("stock AVB0 metadata missing at fixed logical end")
    if stock[-64:-60] != b"AVBf":
        raise SystemExit("stock AVBf footer missing")

    magic, major, minor, original_size, vbmeta_off, vbmeta_size, _ = struct.unpack(
        ">4sIIQQQ28s", stock[-64:])
    if magic != b"AVBf" or major != 1:
        raise SystemExit("unexpected AVB footer format")
    if original_size != logical_end or vbmeta_off != logical_end:
        raise SystemExit("stock AVB footer does not describe the fixed logical end")
    if vbmeta_size <= 0 or vbmeta_off + vbmeta_size > len(stock) - 64:
        raise SystemExit("stock AVB embedded vbmeta bounds invalid")

    out = bytearray(stock)
    out[PAGE:PAGE + stock_kernel_size] = b"\0" * stock_kernel_size
    out[PAGE:PAGE + len(kernel)] = kernel
    out = bytes(out)

    checks = {
        "android_magic": out[:8] == b"ANDROID!",
        "header_page_byte_exact": out[:PAGE] == stock[:PAGE],
        "kernel_region_size_preserved": struct.unpack_from("<I", out, 8)[0] == stock_kernel_size,
        "kernel_payload_prefix_exact": out[PAGE:PAGE + len(kernel)] == kernel,
        "kernel_zero_pad_exact": not any(out[PAGE + len(kernel):PAGE + stock_kernel_size]),
        "stock_ramdisk_offset_preserved": ramdisk_off == align(PAGE + struct.unpack_from("<I", out, 8)[0], PAGE),
        "stock_ramdisk_byte_exact": out[ramdisk_off:ramdisk_off + ramdisk_size] == ramdisk,
        "changed_bytes_outside_kernel_region_zero": out[:PAGE] == stock[:PAGE] and out[PAGE + stock_kernel_size:] == stock[PAGE + stock_kernel_size:],
        "stock_avb0_metadata_byte_exact": out[logical_end:logical_end + vbmeta_size] == stock[logical_end:logical_end + vbmeta_size],
        "stock_avbf_footer_byte_exact": out[-64:] == stock[-64:],
        "partition_size_preserved": len(out) == len(stock),
        "target_release_present": target in out[PAGE:PAGE + len(kernel)],
    }
    failed = [k for k, v in checks.items() if not v]
    args.out.write_bytes(out)

    lines = [
        "C0061_INTEGRATED_BOOT_STATIC_GATE=" + ("PASS" if not failed else "FAIL"),
        "C0061_FIXED_REGION_BOOT_GATE=" + ("PASS" if not failed else "FAIL"),
        f"stock_boot_sha256={sha(stock)}",
        f"new_kernel_sha256={sha(kernel)}",
        f"new_kernel_size={len(kernel)}",
        f"fixed_kernel_region_size={stock_kernel_size}",
        f"kernel_zero_pad_bytes={stock_kernel_size - len(kernel)}",
        f"fixed_ramdisk_offset={ramdisk_off}",
        f"fixed_logical_end={logical_end}",
        f"avb_vbmeta_offset={vbmeta_off}",
        f"avb_vbmeta_size={vbmeta_size}",
        f"new_boot_bytes={len(out)}",
        f"new_boot_sha256={sha(out)}",
        f"target_release={args.target_release}",
    ]
    lines.extend(f"check_{k}={int(v)}" for k, v in checks.items())
    args.validation.write_text("\n".join(lines) + "\n")
    print(args.validation.read_text(), end="")
    if failed:
        raise SystemExit("fixed-region boot validation failed: " + ", ".join(failed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
