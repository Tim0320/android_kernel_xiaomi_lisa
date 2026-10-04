#!/usr/bin/env python3
"""No-build Candidate0059 MIGT/package-runtime source-layout audit.

This does not patch or compile the kernel. It compares the exact pinned Lisa
source against an exact same-generation Xiaomi 5.4 donor and emits a semantic
port map. A PASS means the required source landmarks are present for a bounded
port; it is NOT a runtime/performance pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TARGET_REF = "6e568aabc77a06fa787baec1d9e60e4b559874a3"
DONOR_REPO = "LeviMarvin/android_kernel_xiaomi_alioth"
DONOR_REF = "e7065bc9ead4a0ca183f51101e07dd45a9d5c558"

DONOR_REQUIRED = {
    "drivers/mihw/Kconfig": ("config MIGT", "config PACKAGE_RUNTIME_INFO"),
    "drivers/mihw/Makefile": ("CONFIG_MIGT", "migt.o"),
    "drivers/mihw/migt.c": ("migt_init", "migt_ioctl", '.name = "migt"'),
    "include/linux/pkg_stat.h": ("package_runtime_info", "migt"),
    "kernel/sched/Makefile": (
        "CONFIG_PACKAGE_RUNTIME_INFO",
        "pkg_core.o",
        "pkg_interface.o",
        "migt_sched.o",
        "glk.o",
    ),
    "kernel/sched/pkg_core.c": ("pkg_init",),
    "kernel/sched/pkg_interface.c": ("package_runtime",),
    "kernel/sched/migt_sched.c": ("migt_sched_init", "migt_monitor_hook"),
    "kernel/sched/glk.c": ("game_load_init",),
}

TARGET_REQUIRED = {
    "kernel/sched/walt/walt.c": (
        "walt_update_task_ravg",
        "cpu_util_freq_walt",
        "update_cpu_busy_time",
    ),
    "kernel/sched/walt/walt.h": ("walt_update_task_ravg",),
    "kernel/sched/core.c": ("enqueue_task", "dequeue_task", "walt_update_task_ravg"),
    "kernel/sched/cpufreq_schedutil.c": ("sugov_walt_adjust",),
    "kernel/sched/Makefile": ("CONFIG_SCHED_WALT",),
    "include/linux/sched.h": ("struct task_struct", "struct walt_task_struct"),
    "include/linux/sched/user.h": ("struct user_struct",),
    "kernel/user.c": ("alloc_uid", "free_uid"),
    "kernel/fork.c": ("copy_process",),
    "kernel/exit.c": ("release_task",),
    "kernel/cred.c": ("commit_creds",),
    "kernel/cgroup/cpuset.c": ("cpuset",),
    "kernel/time/timekeeping.c": ("timekeeping",),
}

DONOR_CROSS_CUTTING = (
    "include/linux/sched.h",
    "include/linux/sched/user.h",
    "kernel/user.c",
    "kernel/fork.c",
    "kernel/exit.c",
    "kernel/cred.c",
    "kernel/sysctl.c",
    "kernel/cgroup/cpuset.c",
    "kernel/time/timekeeping.c",
    "kernel/sched/core.c",
    "kernel/sched/cpufreq_schedutil.c",
)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require(root: Path, table: dict[str, tuple[str, ...]], failures: list[str]) -> dict:
    out = {}
    for rel, markers in table.items():
        path = root / rel
        entry = {"exists": path.is_file(), "markers": {}, "sha256": None}
        if not path.is_file():
            failures.append(f"MISSING_FILE:{rel}")
            out[rel] = entry
            continue
        body = text(path)
        entry["sha256"] = sha256(path)
        for marker in markers:
            ok = marker in body
            entry["markers"][marker] = ok
            if not ok:
                failures.append(f"MISSING_MARKER:{rel}:{marker}")
        out[rel] = entry
    return out


def scan_symbol_references(root: Path, symbols: tuple[str, ...]) -> dict:
    result = {symbol: {"references": [], "count": 0} for symbol in symbols}
    allowed = {".c", ".h", ".S", ".Kconfig", ".mk", ""}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if not (name == "Kconfig" or name == "Makefile" or path.suffix in allowed):
            continue
        try:
            lines = text(path).splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(path.relative_to(root))
        for i, line in enumerate(lines, 1):
            for symbol in symbols:
                if symbol in line or (symbol.startswith("CONFIG_") and ("config " + symbol[7:]) in line):
                    result[symbol]["count"] += 1
                    if len(result[symbol]["references"]) < 80:
                        result[symbol]["references"].append({"path": rel, "line": i, "text": line.strip()[:240]})
    return result


def scan_cross_cutting(donor: Path) -> dict:
    result = {}
    needles = ("CONFIG_PACKAGE_RUNTIME_INFO", "pkg.", "pkg_", "migt", "game_load", "glk")
    for rel in DONOR_CROSS_CUTTING:
        path = donor / rel
        if not path.is_file():
            result[rel] = {"exists": False, "hits": []}
            continue
        lines = text(path).splitlines()
        hits = []
        for i, line in enumerate(lines, 1):
            low = line.lower()
            if any(n.lower() in low for n in needles):
                hits.append({"line": i, "text": line.strip()[:240]})
        result[rel] = {"exists": True, "hits": hits[:120]}
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=Path, required=True)
    ap.add_argument("--donor", type=Path, required=True)
    ap.add_argument("--json", type=Path, default=Path("candidate-0059-perf-port-audit.json"))
    ap.add_argument("--text", type=Path, default=Path("candidate-0059-perf-port-audit.txt"))
    args = ap.parse_args()

    failures: list[str] = []
    target_map = require(args.target, TARGET_REQUIRED, failures)
    donor_map = require(args.donor, DONOR_REQUIRED, failures)

    target_flat = (args.target / "kernel/sched/walt.c").is_file()
    target_split = (args.target / "kernel/sched/walt/walt.c").is_file()
    donor_flat = (args.donor / "kernel/sched/walt.c").is_file()
    donor_split = (args.donor / "kernel/sched/walt/walt.c").is_file()

    if not target_split:
        failures.append("TARGET_WALT_SPLIT_LAYOUT_NOT_FOUND")
    if not donor_flat:
        failures.append("DONOR_WALT_FLAT_LAYOUT_NOT_FOUND")

    target_perf_files = [
        "drivers/mihw/migt.c",
        "include/linux/pkg_stat.h",
        "kernel/sched/pkg_core.c",
        "kernel/sched/pkg_interface.c",
        "kernel/sched/migt_sched.c",
        "kernel/sched/glk.c",
    ]
    target_baseline = {rel: (args.target / rel).is_file() for rel in target_perf_files}

    target_kconfig = text(args.target / "drivers/mihw/Kconfig")
    target_makefile = text(args.target / "drivers/mihw/Makefile")
    baseline_config = {
        "MIGT_declared": "config MIGT" in target_kconfig,
        "PACKAGE_RUNTIME_INFO_declared": "config PACKAGE_RUNTIME_INFO" in target_kconfig,
        "migt_object_wired": "CONFIG_MIGT" in target_makefile and "migt.o" in target_makefile,
    }

    raw_patch_safe = not (
        target_split and donor_flat and not target_flat and not donor_split
    )
    strategy = "semantic-hook-map" if not raw_patch_safe else "layout-compatible-review-still-required"

    report = {
        "candidate": "0059",
        "audit": "MIGT/package-runtime no-build source-layout audit",
        "target_ref": TARGET_REF,
        "donor_repo": DONOR_REPO,
        "donor_ref": DONOR_REF,
        "target_walt_layout": {"flat": target_flat, "split": target_split},
        "donor_walt_layout": {"flat": donor_flat, "split": donor_split},
        "raw_donor_patch_safe": raw_patch_safe,
        "required_port_strategy": strategy,
        "target_required_landmarks": target_map,
        "donor_required_chain": donor_map,
        "donor_cross_cutting_hooks": scan_cross_cutting(args.donor),
        "target_perf_files_already_present": target_baseline,
        "target_perf_config_already_present": baseline_config,
        "target_symbol_reference_scan": scan_symbol_references(
            args.target,
            ("CONFIG_MIHW", "CONFIG_MIGT", "CONFIG_PACKAGE_RUNTIME_INFO", "CONFIG_OEM_KERNEL"),
        ),
        "failures": failures,
        "result": "PASS" if not failures else "FAIL",
        "claims": {
            "kernel_compiled": False,
            "runtime_tested": False,
            "jank_fixed": False,
            "safe_to_raw_apply_donor_patch": raw_patch_safe,
        },
    }
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    summary = [
        f"CANDIDATE0059_PERF_PORT_AUDIT={report['result']}",
        f"TARGET_REF={TARGET_REF}",
        f"DONOR={DONOR_REPO}@{DONOR_REF}",
        f"TARGET_WALT_LAYOUT=flat:{int(target_flat)} split:{int(target_split)}",
        f"DONOR_WALT_LAYOUT=flat:{int(donor_flat)} split:{int(donor_split)}",
        f"RAW_DONOR_PATCH_SAFE={str(raw_patch_safe).lower()}",
        f"REQUIRED_PORT_STRATEGY={strategy}",
        "TARGET_PERF_BASELINE=" + json.dumps(target_baseline, sort_keys=True),
        "TARGET_PERF_CONFIG_BASELINE=" + json.dumps(baseline_config, sort_keys=True),
        "TARGET_OEM_KERNEL_REFERENCE_COUNT=" + str(
            report["target_symbol_reference_scan"]["CONFIG_OEM_KERNEL"]["count"]
        ),
    ]
    if failures:
        summary.extend("FAILURE=" + item for item in failures)
    else:
        summary.append(
            "NEXT=map donor package-runtime hooks semantically into Lisa split-WALT/task/user lifecycle before source mutation"
        )
    args.text.write_text("\n".join(summary) + "\n")
    print("\n".join(summary))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
