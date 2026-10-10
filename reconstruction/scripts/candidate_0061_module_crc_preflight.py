#!/usr/bin/env python3
"""C0061 CRC preflight for a compiled NFC .ko versus the *same build* Module.symvers.

Passing DOES NOT establish compatibility of stock Android 5.4.289 vendor modules.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

def imported_crcs(module: Path) -> dict[str, int]:
    objcopy = shutil.which("llvm-objcopy") or shutil.which("aarch64-linux-gnu-objcopy")
    if not objcopy:
        raise RuntimeError("Need llvm-objcopy / aarch64-linux-gnu-objcopy")
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "module.ko"
        dest = Path(td) / "versions.bin"
        # llvm-objcopy without explicit output may rewrite the input file.
        # Never touch the original module; only operate on this disposable copy.
        shutil.copyfile(module, copy)
        subprocess.run([objcopy, "--dump-section", f"__versions={dest}", str(copy)],
                       check=True, capture_output=True, text=True)
        if not dest.is_file():
            raise RuntimeError("Missing __versions; cannot claim CRC coverage")
        buf = dest.read_bytes()
    if not buf or len(buf) % 64:
        raise RuntimeError("Invalid arm64 5.4 modversion_info records")
    parsed = {}
    for off in range(0, len(buf), 64):
        crc, raw_name = struct.unpack_from("<Q56s", buf, off)
        name = raw_name.partition(b"\0")[0].decode("ascii")
        if not name or crc > 0xffffffff or name in parsed:
            raise RuntimeError("Malformed / duplicate modversion record")
        parsed[name] = crc
    return parsed

def exported_crcs(symvers: Path) -> tuple[dict[str, int], list[str]]:
    exports, ambiguous = {}, set()
    for lineno, line in enumerate(symvers.read_text().splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 4 or not parts[0].startswith("0x"):
            raise RuntimeError(f"Malformed Module.symvers line {lineno}")
        crc, symbol = int(parts[0], 16), parts[1]
        if crc > 0xffffffff:
            raise RuntimeError("CRC exceeds 32-bit")
        if symbol in exports and exports[symbol] != crc:
            ambiguous.add(symbol)
        exports[symbol] = crc
    return exports, sorted(ambiguous)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--module", type=Path, required=True)
    p.add_argument("--symvers", type=Path, required=True)
    p.add_argument("--json", type=Path, required=True)
    p.add_argument("--expected-sha256", required=True)
    p.add_argument("--expected-kernelrelease", required=True)
    args = p.parse_args()
    data = args.module.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != args.expected_sha256 or data[:6] != b"\x7fELF\x02\x01":
        raise SystemExit("C0061_NFC_CRC_PREFLIGHT=FAIL: module SHA/ELF identity")
    parts = data.split(b"vermagic=", 1)
    vermagic = parts[1].split(b"\0", 1)[0].decode("ascii", "replace") if len(parts) == 2 else ""
    imported = imported_crcs(args.module)
    exported, ambiguous = exported_crcs(args.symvers)
    missing = sorted(set(imported) - set(exported))
    mismatches = [{"symbol": n, "module_crc": f"0x{v:08x}", "build_crc": f"0x{exported[n]:08x}"}
                  for n,v in sorted(imported.items()) if n in exported and v != exported[n]]
    ok = not (missing or mismatches or ambiguous) and vermagic.startswith(args.expected_kernelrelease + " ")
    result = {
        "result": "PASS" if ok else "FAIL",
        "scope": "COMPILED_NFC_VS_SAME_BUILD_MODULE_SYMVERS_ONLY_NOT_DEVICE_VENDOR_COMPATIBILITY",
        "module_sha256": sha, "module_vermagic": vermagic,
        "imported_crc_symbols": len(imported),
        "matched_crc_symbols": len(imported) - len(missing) - len(mismatches),
        "missing_symbols": missing, "mismatches": mismatches,
        "ambiguous_exports": ambiguous,
        "device_5_4_289_modules_analyzed": False,
        "android_runtime_load_verified": False,
        "device_boot_pass": False,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("C0061_NFC_CRC_PREFLIGHT=" + result["result"])
    print("C0061_NFC_IMPORTED_SYMBOLS=" + str(len(imported)))
    print("C0061_NFC_MATCHED_SYMBOLS=" + str(result["matched_crc_symbols"]))
    print("C0061_VENDOR_5_4_289_CRC_COMPATIBILITY=UNVERIFIED")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
