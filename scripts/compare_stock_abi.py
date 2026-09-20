#!/usr/bin/env python3
"""
Compare a reconstructed kernel Module.symvers against stock HyperOS modules.

Usage:
  python3 scripts/compare_stock_abi.py \
      --symvers out/Module.symvers \
      --modules /path/to/vendor/lib/modules

Requires: modinfo, readelf, nm (binutils/kmod).
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import re
import shutil
import subprocess
import sys


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)


def load_symvers(path: pathlib.Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(errors="replace").splitlines():
        cols = line.split()
        if len(cols) >= 2:
            result[cols[1]] = cols[0].lower()
    return result


def modinfo(path: pathlib.Path, field: str) -> str:
    try:
        return run("modinfo", "-F", field, str(path)).strip()
    except subprocess.CalledProcessError:
        return ""


def undefined_symbols(path: pathlib.Path) -> list[str]:
    out = run("nm", "-u", str(path))
    syms = []
    for line in out.splitlines():
        sym = line.strip().split()[-1] if line.strip() else ""
        if sym:
            syms.append(sym)
    return sorted(set(syms))


def version_crcs(path: pathlib.Path) -> dict[str, str]:
    """
    Extract __versions records from ELF. Android 5.4 arm64 modules generally use
    a 64-bit CRC followed by a fixed-size symbol name record.
    """
    raw = subprocess.check_output(
        ["readelf", "-x", "__versions", str(path)],
        stderr=subprocess.DEVNULL,
        text=True,
    )
    hex_words: list[str] = []
    for line in raw.splitlines():
        m = re.match(r"\s*0x[0-9a-fA-F]+\s+((?:[0-9a-fA-F]{8}\s+){1,4})", line)
        if m:
            hex_words.extend(m.group(1).split())
    if not hex_words:
        return {}

    data = bytes.fromhex("".join(hex_words))
    record = 64
    result: dict[str, str] = {}
    for off in range(0, len(data) - record + 1, record):
        chunk = data[off : off + record]
        crc = int.from_bytes(chunk[0:8], "little")
        name = chunk[8:].split(b"\0", 1)[0].decode("ascii", "ignore")
        if name:
            result[name] = f"0x{crc:08x}"
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symvers", required=True, type=pathlib.Path)
    ap.add_argument("--modules", required=True, type=pathlib.Path)
    ap.add_argument("--csv", type=pathlib.Path, default=pathlib.Path("abi-report.csv"))
    ns = ap.parse_args()

    for tool in ("modinfo", "readelf", "nm"):
        if not shutil.which(tool):
            sys.exit(f"missing required tool: {tool}")

    symvers = load_symvers(ns.symvers)
    modules = sorted(ns.modules.rglob("*.ko"))
    if not modules:
        sys.exit(f"no .ko files found under {ns.modules}")

    rows = []
    mismatches = 0
    for ko in modules:
        stock_crc = version_crcs(ko)
        for symbol in undefined_symbols(ko):
            stock = stock_crc.get(symbol, "")
            rebuilt = symvers.get(symbol, "")
            status = "UNKNOWN"
            if rebuilt and stock:
                status = "MATCH" if rebuilt.lower() == stock.lower() else "CRC_MISMATCH"
            elif rebuilt:
                status = "NO_STOCK_CRC"
            elif stock:
                status = "MISSING_PROVIDER"
            if status in {"CRC_MISMATCH", "MISSING_PROVIDER"}:
                mismatches += 1
            rows.append({
                "module": ko.name,
                "vermagic": modinfo(ko, "vermagic"),
                "symbol": symbol,
                "stock_crc": stock,
                "rebuilt_crc": rebuilt,
                "status": status,
            })

    with ns.csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    print(f"modules={len(modules)} symbol_checks={len(rows)} mismatches={mismatches}")
    print(f"report={ns.csv}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
