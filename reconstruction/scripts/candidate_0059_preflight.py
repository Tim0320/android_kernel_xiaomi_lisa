#!/usr/bin/env python3
"""Candidate0059 two-stage readiness/acceptance gate.

PREBUILD blocks the first full CI59 build until source/config wiring and the
Developer Options debug-property provenance/fix are resolved.
POSTDEVICE reuses PREBUILD and then validates collected real-device evidence.

This script is read-only. It never flashes a phone or weakens SELinux.
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
EXPECTED_STOCK_PROPS = {
    "ro.debuggable": "0",
    "ro.force.debuggable": "0",
    "ro.secure": "1",
    "ro.adb.secure": "1",
}
ALLOWED_IORAP_STRATEGIES = {
    "stock-faithful-disable",
    "semantic-5.4-port",
    "defer-outside-c0059",
}
FORBIDDEN_DEBUG_FIX_TOKENS = (
    "setenforce 0",
    "permissive=1",
    "global permissive",
    "broad system_app allow",
    "fake property",
    "fake property_service",
    "kernel-bpf workaround",
)


def read_text(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def load_props(path: Path | None) -> dict[str, str]:
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
        elif "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def load_json(path: Path | None) -> dict:
    text = read_text(path).strip()
    if not text:
        return {}
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def add_failure(failures: list[str], code: str, detail: str) -> None:
    failures.append(f"{code}: {detail}")


def scan_unsafe_alias(source_root: Path) -> list[str]:
    hits: list[str] = []
    for top in ("drivers", "kernel", "include"):
        root = source_root / top
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix not in {".c", ".h", ".S"}:
                continue
            body = read_text(p).lower()
            if "migt" in body and "metis" in body and (
                "miscdevice" in body or "device_create" in body
            ):
                hits.append(str(p.relative_to(source_root)))
    return sorted(set(hits))


def prebuild(args: argparse.Namespace, failures: list[str]) -> None:
    cfg = read_text(args.config)
    missing_cfg = [item for item in REQUIRED_CONFIG if item not in cfg]
    if missing_cfg:
        add_failure(failures, "PERF_CONFIG_NOT_RESTORED", ", ".join(missing_cfg))

    for rel, symbol in REQUIRED_SYMBOLS.items():
        body = read_text(args.source_root / rel)
        if not body or symbol not in body:
            add_failure(
                failures,
                "PERF_SOURCE_CHAIN_INCOMPLETE",
                f"{rel} missing {symbol}",
            )

    sched_makefile = read_text(args.source_root / "kernel/sched/Makefile")
    missing_obj = [item for item in REQUIRED_SCHED_OBJECTS if item not in sched_makefile]
    if missing_obj:
        add_failure(
            failures,
            "PACKAGE_RUNTIME_WIRING_INCOMPLETE",
            ", ".join(missing_obj),
        )

    stock = load_props(args.stock_props)
    for key, expected in EXPECTED_STOCK_PROPS.items():
        if stock.get(key) != expected:
            add_failure(
                failures,
                "STOCK_RUNTIME_BASELINE_UNEXPECTED",
                f"{key}={stock.get(key)!r}, expected {expected!r}",
            )

    evidence = load_json(args.debug_evidence)
    required_evidence = (
        "resolved",
        "first_override_path_proven",
        "ro_secure_zero_source_resolved",
        "override_source",
        "fix_location",
        "source_evidence",
        "affected_files",
    )
    missing = [key for key in required_evidence if not evidence.get(key)]
    if missing:
        add_failure(
            failures,
            "DEBUG_OVERRIDE_SOURCE_UNRESOLVED",
            "missing/false fields: " + ", ".join(missing),
        )
    else:
        if evidence.get("resolved") is not True:
            add_failure(failures, "DEBUG_OVERRIDE_SOURCE_UNRESOLVED", "resolved != true")
        if evidence.get("first_override_path_proven") is not True:
            add_failure(
                failures,
                "DEBUG_OVERRIDE_PATH_UNPROVEN",
                "first_override_path_proven != true",
            )
        if evidence.get("ro_secure_zero_source_resolved") is not True:
            add_failure(
                failures,
                "RO_SECURE_ZERO_SOURCE_UNRESOLVED",
                "ro_secure_zero_source_resolved != true",
            )
        evidence_text = json.dumps(evidence, sort_keys=True).lower()
        for token in FORBIDDEN_DEBUG_FIX_TOKENS:
            if token in evidence_text:
                add_failure(
                    failures,
                    "UNSAFE_DEVELOPER_OPTIONS_FIX",
                    f"forbidden approach found: {token}",
                )

    if args.iorap_strategy not in ALLOWED_IORAP_STRATEGIES:
        add_failure(
            failures,
            "IORAP_STRATEGY_UNRESOLVED",
            f"{args.iorap_strategy!r} not in {sorted(ALLOWED_IORAP_STRATEGIES)}",
        )

    alias_hits = scan_unsafe_alias(args.source_root)
    if alias_hits:
        add_failure(
            failures,
            "UNSAFE_MIGT_METIS_ALIAS",
            ", ".join(alias_hits),
        )


def postdevice(args: argparse.Namespace, failures: list[str]) -> None:
    candidate = load_props(args.candidate_props)
    stock = load_props(args.stock_props)
    if not candidate:
        add_failure(failures, "CANDIDATE_RUNTIME_PROPS_MISSING", "no candidate props")
    else:
        for key in EXPECTED_STOCK_PROPS:
            if candidate.get(key) != stock.get(key):
                add_failure(
                    failures,
                    "CANDIDATE_RUNTIME_DEBUG_PROPS_DIVERGE",
                    f"{key}: stock={stock.get(key)!r} candidate={candidate.get(key)!r}",
                )

    log_text = read_text(args.developer_options_log)
    if not log_text:
        add_failure(
            failures,
            "DEVELOPER_OPTIONS_RUNTIME_EVIDENCE_MISSING",
            "developer options log not supplied/empty",
        )
    else:
        low = log_text.lower()
        if "logpersistd_logging_prop" in low and ("avc: denied" in low or "access denied" in low):
            add_failure(
                failures,
                "LOGPERSISTD_DENIAL_PRESENT",
                "runtime log still contains logpersistd property denial",
            )
        if "abstractlogpersistpreferencecontroller" in low and (
            "fatal exception" in low or "runtimeexception" in low
        ):
            add_failure(
                failures,
                "DEVELOPER_OPTIONS_SETTINGS_FATAL_PRESENT",
                "Settings still crashes in logpersist controller",
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=("prebuild", "postdevice"), required=True)
    ap.add_argument("--source-root", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--stock-props", type=Path, required=True)
    ap.add_argument("--debug-evidence", type=Path, required=True)
    ap.add_argument("--iorap-strategy", required=True)
    ap.add_argument("--candidate-props", type=Path)
    ap.add_argument("--developer-options-log", type=Path)
    args = ap.parse_args()

    failures: list[str] = []
    try:
        prebuild(args, failures)
        if args.phase == "postdevice":
            postdevice(args, failures)
    except (json.JSONDecodeError, ValueError) as exc:
        add_failure(failures, "INPUT_PARSE_ERROR", str(exc))

    if failures:
        print(f"CANDIDATE0059_{args.phase.upper()}=FAIL")
        for item in failures:
            print(item)
        return 1

    print(f"CANDIDATE0059_{args.phase.upper()}=PASS")
    if args.phase == "prebuild":
        print("Source/config/provenance gate passed; this only permits starting one CI59 build.")
    else:
        print("Runtime property and Developer Options evidence gate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
