#!/usr/bin/env python3
"""Read-only, offline CRC check: stock Lisa NFC modules versus C0061 Module.symvers.

Accepts paths to PRIVATE binaries. Do not commit or upload OEM .ko contents.
PASS only means imported symbol CRCs match the supplied kernel export table;
it does NOT prove that the Android loader accepts or loads either module.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from candidate_0061_module_crc_preflight import imported_crcs, exported_crcs

EXPECTED = {
    "qgki": "b37dae41aad83b6adaa1f2a16253d2a8ca931b83a534fd5fb57ceaea2424bc68",
    "gki": "bb1e8994d0ddf0b15bd038457a850b2a8b5c7b74e1816b97dea5623c2ea5c80b",
}

def compare(label: str, p: Path, exports: dict[str, int]) -> dict:
    data = p.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != EXPECTED[label]:
        raise RuntimeError(f"{label}: device NFC ELF SHA256 changed: {sha}")
    if len(data) < 20 or data[:6] != bytes.fromhex("7f454c460201") or int.from_bytes(data[18:20], "little") != 183:
        raise RuntimeError(f"{label}: not ELF64 little-endian AArch64")
    tag = data.find(b"vermagic=")
    if tag == -1:
        raise RuntimeError(f"{label}: ELF vermagic tag missing")
    magic = data[tag + len(b"vermagic="):].split(b"\0", 1)[0].decode("ascii", "replace")
    versions = imported_crcs(p)
    if "module_layout" not in versions:
        raise RuntimeError(f"{label}: no module_layout modversion CRC")
    missing = sorted(set(versions) - set(exports))
    changed = [{
        "name": symbol, "stock_crc": f"0x{crc:08x}", "kernel_crc": f"0x{exports[symbol]:08x}"
    } for symbol, crc in sorted(versions.items())
       if symbol in exports and crc != exports[symbol]]
    return {
        "branch": label, "sha256": sha, "vermagic": magic,
        "imported": len(versions), "matched": len(versions) - len(missing) - len(changed),
        "missing": missing, "different_crcs": changed,
        "all_imported_crcs_match": not missing and not changed,
        "module_layout_matches": versions["module_layout"] == exports.get("module_layout"),
        "android_load_tested": False,
    }

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qgki", type=Path, required=True, help="PRIVATE stock /vendor/lib/modules/nfc_i2c.ko")
    ap.add_argument("--gki", type=Path, required=True, help="PRIVATE stock /vendor/lib/modules/5.4-gki/nfc_i2c.ko")
    ap.add_argument("--symvers", type=Path, required=True, help="Module.symvers from C0061 run 37655937871")
    ap.add_argument("--json", type=Path, required=True)
    args = ap.parse_args()
    exports, ambiguous = exported_crcs(args.symvers)
    if not exports or ambiguous:
        raise RuntimeError(f"invalid Module.symvers: ambiguous exports={ambiguous[:5]}")
    reports = [compare("qgki", args.qgki, exports), compare("gki", args.gki, exports)]
    result = {
        "scope": "OFFLINE_STOCK_NFC_ELF_CRC_VS_INTEGRATED_C0061_ONLY",
        "source_build_run": 37655937871,
        "stock_vendor_module_bytes_published": False,
        "android_actual_loader_branch": "UNKNOWN",
        "device_boot_pass": False,
        "reports": reports,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    for r in reports:
        print(f"{r['branch']} imported={r['imported']} matched={r['matched']} "
              f"missing={len(r['missing'])} different={len(r['different_crcs'])}")
    print("DEVICE_BOOT_PASS=UNVERIFIED")
    return 0 if reports[0]["all_imported_crcs_match"] and not reports[1]["all_imported_crcs_match"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
