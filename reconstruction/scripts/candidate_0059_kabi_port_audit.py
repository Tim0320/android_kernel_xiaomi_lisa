#!/usr/bin/env python3
"""Candidate0059 Android KABI strategy audit for package-runtime state.

Read-only audit. It proves that the stock-style package_runtime_info object is
too large to embed into one 64-bit KABI slot and validates a pointer-backed
port strategy that consumes exactly one reserved u64 in task_struct and one in
user_struct while preserving GENKSYMS-visible ABI.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TARGET_REF = "6e568aabc77a06fa787baec1d9e60e4b559874a3"
DONOR_REPO = "LeviMarvin/android_kernel_xiaomi_alioth"
DONOR_REF = "e7065bc9ead4a0ca183f51101e07dd45a9d5c558"

TASK_RESERVE = 8
USER_RESERVE = 2


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def fail(items: list[str], code: str, detail: str) -> None:
    items.append(f"{code}:{detail}")


def struct_block(body: str, name: str) -> str:
    start = body.find(f"struct {name} {{")
    if start < 0:
        return ""
    depth = 0
    end = start
    seen = False
    for i in range(start, len(body)):
        ch = body[i]
        if ch == "{":
            depth += 1
            seen = True
        elif ch == "}":
            depth -= 1
            if seen and depth == 0:
                end = i + 1
                break
    return body[start:end]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=Path, required=True)
    ap.add_argument("--donor", type=Path, required=True)
    ap.add_argument("--json", type=Path, required=True)
    ap.add_argument("--text", type=Path, required=True)
    args = ap.parse_args()

    failures: list[str] = []

    kabi_h = text(args.target / "include/linux/android_kabi.h")
    sched_h = text(args.target / "include/linux/sched.h")
    user_h = text(args.target / "include/linux/sched/user.h")
    pkg_h = text(args.donor / "include/linux/pkg_stat.h")

    task_block = struct_block(sched_h, "task_struct")
    user_block = struct_block(user_h, "user_struct")
    pkg_block = struct_block(pkg_h, "package_runtime_info")

    if not task_block:
        fail(failures, "TASK_STRUCT_NOT_FOUND", "include/linux/sched.h")
    if not user_block:
        fail(failures, "USER_STRUCT_NOT_FOUND", "include/linux/sched/user.h")
    if not pkg_block:
        fail(failures, "DONOR_PACKAGE_RUNTIME_INFO_NOT_FOUND", "include/linux/pkg_stat.h")

    task_marker = f"ANDROID_KABI_RESERVE({TASK_RESERVE});"
    user_marker = f"ANDROID_KABI_RESERVE({USER_RESERVE});"
    if task_marker not in task_block:
        fail(failures, "TASK_RESERVE_MISSING", task_marker)
    if user_marker not in user_block:
        fail(failures, "USER_RESERVE_MISSING", user_marker)

    # Baseline must still be untouched before the source port is generated.
    if f"ANDROID_KABI_USE({TASK_RESERVE}" in task_block:
        fail(failures, "TASK_RESERVE_ALREADY_CONSUMED", str(TASK_RESERVE))
    if f"ANDROID_KABI_USE({USER_RESERVE}" in user_block:
        fail(failures, "USER_RESERVE_ALREADY_CONSUMED", str(USER_RESERVE))

    # Prove the Android KABI macro retains the old reserve under __GENKSYMS__
    # and enforces size/alignment in normal compilation.
    required_kabi = (
        "#define ANDROID_KABI_USE(number, _new)",
        "#ifdef __GENKSYMS__",
        "_ANDROID_KABI_REPLACE(_ANDROID_KABI_RESERVE(number), _new)",
        "_Static_assert(sizeof(struct{_new;}) <= sizeof(struct{_orig;}),",
    )
    for marker in required_kabi:
        if marker not in kabi_h:
            fail(failures, "ANDROID_KABI_CONTRACT_MISSING", marker)

    # Donor object is manifestly much larger than one u64: lock, list, multiple
    # six-element u64 arrays and nested MIGT state. This semantic check avoids
    # pretending an 8-byte reserve can contain the full object.
    large_markers = (
        "rwlock_t lock;",
        "struct list_head list;",
        "u64 sup_cluster_runtime[HISTORY_WINDOWS];",
        "u64 front_runtime[HISTORY_WINDOWS][MAX_CLUSTER];",
        "cpumask_t cpus_allowed;",
        "u32 bucket[NUM_MIGT_BUCKETS];",
    )
    for marker in large_markers:
        if marker not in pkg_block:
            fail(failures, "DONOR_SIZE_EVIDENCE_MISSING", marker)

    # Target is arm64; a pointer is 8 bytes and is the only state placed in
    # each KABI slot. The full object is dynamically allocated outside the
    # frozen structures.
    arm64 = (args.target / "arch/arm64").is_dir()
    if not arm64:
        fail(failures, "TARGET_NOT_ARM64", "arch/arm64 missing")

    plan = {
        "task_struct": {
            "slot": TASK_RESERVE,
            "replacement": "struct package_runtime_info *pkg_rt",
            "macro": f"ANDROID_KABI_USE({TASK_RESERVE}, struct package_runtime_info *pkg_rt);",
            "external_state": True,
        },
        "user_struct": {
            "slot": USER_RESERVE,
            "replacement": "struct package_runtime_info *pkg_rt",
            "macro": f"ANDROID_KABI_USE({USER_RESERVE}, struct package_runtime_info *pkg_rt);",
            "external_state": True,
        },
        "allocation_policy": {
            "task": "allocate/initialize in copy_process after dup_task_struct and before package list membership; free on every failure/release path",
            "user": "allocate/initialize when user_struct is created; free immediately before final user_struct destruction",
        },
        "access_policy": "port donor p->pkg/user->pkg accesses through helper accessors; do not expose raw /dev/metis alias",
    }

    report = {
        "candidate": "0059",
        "target_ref": TARGET_REF,
        "donor_repo": DONOR_REPO,
        "donor_ref": DONOR_REF,
        "result": "PASS" if not failures else "FAIL",
        "target_arm64": arm64,
        "full_package_runtime_info_fits_one_u64": False,
        "pointer_backed_strategy": plan,
        "failures": failures,
        "claims": {
            "source_mutated": False,
            "compiled": False,
            "runtime_tested": False,
            "abi_runtime_validated": False,
        },
    }
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    lines = [
        f"CANDIDATE0059_KABI_PORT_AUDIT={report['result']}",
        f"TARGET_REF={TARGET_REF}",
        f"DONOR={DONOR_REPO}@{DONOR_REF}",
        "FULL_PACKAGE_RUNTIME_INFO_FITS_ONE_U64=false",
        f"TASK_KABI_SLOT={TASK_RESERVE}",
        f"USER_KABI_SLOT={USER_RESERVE}",
        "PORT_STRATEGY=pointer-backed-external-state",
        "GENKSYMS_POLICY=preserve-original-reserve",
    ]
    if failures:
        lines.extend("FAILURE=" + x for x in failures)
    else:
        lines.append("NEXT=generate bounded stage1 source patch using pointer-backed state and exhaustive lifecycle cleanup")
    args.text.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
