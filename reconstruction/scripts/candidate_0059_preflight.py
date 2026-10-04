#!/usr/bin/env python3
"""Candidate0059 no-build readiness gate.

This script intentionally blocks a full Candidate0059 build until both
Developer Options and Android16 performance repair tracks have source-level
evidence. It does not modify a phone, boot image, SELinux policy, or kernel.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_CONFIG = (
    "CONFIG_MIHW=y",
    "CONFIG_MIGT=y",
    "CONFIG_PACKAGE_RUNTIME_INFO=y",
    "CONFIG_OEM_KERNEL=y",
)

REQUIRED_SYMBOLS = {
    "drivers/mihw/migt.c": "migt_init",
    "kernel/sched/migt_sched.c": "migt_sched_init",
    "kernel/sched/glk.c": "game_load_init",
    "kernel/sched/pkg_core.c": "pkg_init",
}

REQUIRED_SCHED_OBJECTS = ("pkg_core.o", "pkg_interface.o", "migt_sched.o", "glk.o")
EXPECTED_USER_PROPS = {
    "ro.debuggable": "0",
    "ro.force.debuggable": "0",
    "ro.secure": "1",
    "ro.adb.secure": "1",
}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def load_props(path: Path) -> dict[str, str]:
    text = read_text(path).strip()
    if not text:
        return {}
    if text.startswith("{"):
        raw = json.loads(text)
        return {str(k): str(v) for k, v in raw.items()}
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"\[([^\]]+)\]\s*:\s*\[([^\]]*)\]", line)
        if m:
            out[m.group(1)] = m.group(2)
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def fail(code: str, detail: str, failures: list[str]) -> None:
    failures.append(f"{code}: {detail}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-root", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--stock-props", type=Path, required=True)
    ap.add_argument("--candidate-props", type=Path, required=True)
    ap.add_argument(
        "--debug-override-source",
        default="",
        help="Resolved early-boot source/fix location for debug property divergence",
    )
    args = ap.parse_args()

    failures: list[str] = []
    cfg = read_text(args.config)

    missing_cfg = [x for x in REQUIRED_CONFIG if x not in cfg]
    if missing_cfg:
        fail("PERF_CONFIG_NOT_RESTORED", ", ".join(missing_cfg), failures)

    for rel, symbol in REQUIRED_SYMBOLS.items():
        body = read_text(args.source_root / rel)
        if not body or symbol not in body:
            fail("PERF_SOURCE_CHAIN_INCOMPLETE", f"{rel} missing {symbol}", failures)

    sched_makefile = read_text(args.source_root / "kernel/sched/Makefile")
    missing_obj = [x for x in REQUIRED_SCHED_OBJECTS if x not in sched_makefile]
    if missing_obj:
        fail("PACKAGE_RUNTIME_WIRING_INCOMPLETE", ", ".join(missing_obj), failures)

    stock = load_props(args.stock_props)
    cand = load_props(args.candidate_props)

    for key, expected in EXPECTED_USER_PROPS.items():
        if stock.get(key) != expected:
            fail("STOCK_RUNTIME_BASELINE_UNEXPECTED", f"{key}={stock.get(key)!r}", failures)
        if cand.get(key) != stock.get(key):
            fail(
                "CANDIDATE_RUNTIME_DEBUG_PROPS_DIVERGE",
                f"{key}: stock={stock.get(key)!r} candidate={cand.get(key)!r}",
                failures,
            )

    if not args.debug_override_source.strip():
        fail(
            "DEBUG_OVERRIDE_SOURCE_UNRESOLVED",
            "early source/fix location for ro.debuggable/ro.force.debuggable/ro.secure/ro.adb.secure is unresolved",
            failures,
        )

    # Explicitly reject the unsafe compatibility shortcut discussed during 0059 triage.
    scan_roots = [
        args.source_root / "drivers",
        args.source_root / "kernel",
        args.source_root / "include",
    ]
    alias_hits: list[str] = []
    for root in scan_roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix not in {".c", ".h", ".S"}:
                continue
            body = read_text(p)
            low = body.lower()
            if "migt" in low and "metis" in low and ("miscdevice" in low or "device_create" in low):
                alias_hits.append(str(p.relative_to(args.source_root)))
    if alias_hits:
        fail(
            "UNSAFE_MIGT_METIS_ALIAS",
            "same implementation appears to expose both MIGT and Metis device identities: "
            + ", ".join(sorted(set(alias_hits))),
            failures,
        )

    if failures:
        print("CANDIDATE0059_PREFLIGHT=FAIL")
        for item in failures:
            print(item)
        return 1

    print("CANDIDATE0059_PREFLIGHT=PASS")
    print("GoalA runtime property baseline matches stock and override source is resolved.")
    print("GoalB MIGT/package-runtime config, source chain and scheduler wiring are present.")
    print("This is a no-build readiness PASS only; real-device validation is still required.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
