#!/usr/bin/env python3
"""Read-only ELF imported-symbol export-provider preflight for Candidate0061.

A matching symbol CRC only proves symbol-version consistency. This secondary
gate checks if imports are from vmlinux or from another built module. It does
not establish that the stock Android loader selects/loads an OEM module.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path
from candidate_0061_module_crc_preflight import imported_crcs


def parse_exports(path: Path) -> dict[str, tuple[int, str, str]]:
    exports: dict[str, tuple[int, str, str]] = {}
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 4 or not parts[0].startswith("0x"):
            raise RuntimeError(f"Malformed symvers line {lineno}")
        crc = int(parts[0], 16)
        symbol, provider, export_type = parts[1:4]
        if crc > 0xffffffff:
            raise RuntimeError(f"Invalid CRC at line {lineno}")
        record = (crc, provider, export_type)
        if symbol in exports and exports[symbol] != record:
            raise RuntimeError(f"Ambiguous exported symbol: {symbol}")
        exports[symbol] = record
    if not exports:
        raise RuntimeError("Empty symbol export table")
    return exports


def inspect(module: Path, symvers: Path, require_vmlinux: bool) -> dict:
    imports = imported_crcs(module)
    exports = parse_exports(symvers)
    missing = sorted(set(imports) - set(exports))
    mismatch = sorted(name for name in imports
                      if name in exports and imports[name] != exports[name][0])
    non_vmlinux = [{"symbol": name, "provider": exports[name][1]}
                   for name in imports if name in exports
                   and exports[name][1] != "vmlinux"]
    # Sort mappings explicitly to avoid comparing dicts.
    non_vmlinux.sort(key=lambda item: (item["provider"], item["symbol"]))
    providers = dict(sorted(collections.Counter(
        exports[name][1] for name in imports if name in exports
    ).items()))
    ok = (not missing and not mismatch and
          (not require_vmlinux or not non_vmlinux) and "module_layout" in imports)
    return {
        "result": "PASS" if ok else "FAIL",
        "scope": "STATIC_IMPORT_CRC_EXPORT_PROVIDER_ONLY_NOT_ANDROID_DEVICE_LOAD",
        "module_sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
        "imported_symbols": len(imports),
        "provider_counts": providers,
        "non_vmlinux_imports": non_vmlinux,
        "missing_symbols": missing,
        "crc_mismatch_symbols": mismatch,
        "require_vmlinux": require_vmlinux,
        "android_runtime_verified": False,
        "device_boot_pass": False,
    }


def self_test() -> None:
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as td:
        test = Path(td) / "table.symvers"
        test.write_text("0x00000001\tmodule_layout\tvmlinux\tEXPORT_SYMBOL\t\n"
                        "0x00000002\tfoo\tdrivers/foo\tEXPORT_SYMBOL\t\n")
        parsed = parse_exports(test)
        assert parsed["module_layout"][1] == "vmlinux"
        assert parsed["foo"][1] == "drivers/foo"
        try:
            test.write_text(test.read_text() +
                            "0x00000002\tfoo\tdrivers/bar\tEXPORT_SYMBOL\t\n")
            parse_exports(test)
        except RuntimeError as exc:
            assert "Ambiguous" in str(exc)
        else:
            raise AssertionError("Ambiguous symbol providers not detected")
    print("C0061_NFC_PROVIDER_SELF_TEST=PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path)
    parser.add_argument("--symvers", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--require-vmlinux", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.module or not args.symvers or not args.json:
        parser.error("--module, --symvers and --json are required")
    result = inspect(args.module, args.symvers, args.require_vmlinux)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("C0061_NFC_EXPORT_PROVIDER_GATE=" + result["result"])
    print("C0061_NFC_VMLINUX_IMPORTS=" + str(result["provider_counts"].get("vmlinux", 0)))
    print("C0061_NFC_NONVMLINUX_IMPORTS=" + str(len(result["non_vmlinux_imports"])))
    print("ANDROID_DEVICE_BOOT_PASS=UNVERIFIED")
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
