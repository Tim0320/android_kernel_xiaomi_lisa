#!/usr/bin/env python3
"""Candidate0059 semantic hook map for MIGT/package-runtime.

Read-only no-build audit. It verifies exact donor hook sites and exact Lisa
semantic landing points while preserving Lisa's split-WALT and Android KABI
layout. PASS means the hook map is reproducible; it does NOT mean the port has
been applied, compiled, or runtime-tested.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TARGET_REF = "6e568aabc77a06fa787baec1d9e60e4b559874a3"
DONOR_REPO = "LeviMarvin/android_kernel_xiaomi_alioth"
DONOR_REF = "e7065bc9ead4a0ca183f51101e07dd45a9d5c558"

DONOR_HOOKS = {
    "kernel/fork.c": (
        "INIT_LIST_HEAD(&p->pkg.list);",
        "list_del(&p->pkg.list);",
    ),
    "kernel/exit.c": (
        "list_del(&(p->pkg.list));",
    ),
    "kernel/cred.c": (
        "list_add(&p->pkg.list",
        "list_del(&task->pkg.list)",
    ),
    "kernel/sched/core.c": (
        "migt_monitor_hook",
    ),
    "kernel/cgroup/cpuset.c": (
        "current->pkg.migt.flag",
        "current->pkg.migt.cpus_allowed",
    ),
    "include/linux/sched.h": (
        "struct package_runtime_info pkg;",
    ),
    "include/linux/sched/user.h": (
        "struct package_runtime_info pkg;",
    ),
}

TARGET_LANDMARKS = {
    "kernel/fork.c": (
        "p = dup_task_struct(current, node);",
        "copy_creds(p, clone_flags)",
        "bad_fork_cleanup_count:",
    ),
    "kernel/exit.c": (
        "void release_task(struct task_struct *p)",
        "__exit_signal(p);",
    ),
    "kernel/cred.c": (
        "int commit_creds(struct cred *new)",
        "struct cred *prepare_creds(void)",
    ),
    "kernel/sched/core.c": (
        "static inline void enqueue_task(",
        "static inline void dequeue_task(",
        "walt_update_task_ravg",
    ),
    "kernel/sched/walt/walt.c": (
        "void walt_update_task_ravg(",
        "static void update_cpu_busy_time(",
        "cpu_util_freq_walt(",
    ),
    "kernel/cgroup/cpuset.c": (
        "set_cpus_allowed_ptr",
        "update_tasks_cpumask",
        "cpuset_can_attach",
    ),
    "include/linux/sched.h": (
        "struct task_struct {",
        "struct walt_task_struct",
        "ANDROID_KABI_RESERVE(8);",
    ),
    "include/linux/sched/user.h": (
        "struct user_struct {",
        "ANDROID_KABI_RESERVE(1);",
        "ANDROID_KABI_RESERVE(2);",
    ),
}

MUST_NOT_EXIST_TARGET = (
    "drivers/mihw/migt.c",
    "include/linux/pkg_stat.h",
    "kernel/sched/pkg_core.c",
    "kernel/sched/pkg_interface.c",
    "kernel/sched/migt_sched.c",
    "kernel/sched/glk.c",
)

PORT_PLAN = [
    {
        "area": "task_struct",
        "donor": "include/linux/sched.h direct struct package_runtime_info pkg",
        "target": "include/linux/sched.h task_struct Android KABI reserve area",
        "action": "DO_NOT append raw field. Consume an appropriate Android KABI reserve only after size/alignment and stock ABI proof.",
        "risk": "critical-kabi",
    },
    {
        "area": "user_struct",
        "donor": "include/linux/sched/user.h direct package_runtime_info pkg",
        "target": "include/linux/sched/user.h ANDROID_KABI_RESERVE(1..2)",
        "action": "Use Android KABI reserve mechanism rather than raw append; validate structure size/offset contract.",
        "risk": "critical-kabi",
    },
    {
        "area": "task-lifecycle",
        "donor": "fork/exit/cred package list init/add/del",
        "target": "copy_process after dup_task_struct / credential transitions / release_task",
        "action": "Port guarded package-list lifecycle semantically at target lifecycle landmarks.",
        "risk": "high",
    },
    {
        "area": "scheduler-monitor",
        "donor": "kernel/sched/core.c migt_monitor_hook",
        "target": "Lisa enqueue/dequeue + split-WALT update path",
        "action": "Map hook semantics into Lisa event ordering; do not paste donor flat-WALT patch.",
        "risk": "high",
    },
    {
        "area": "walt-accounting",
        "donor": "flat kernel/sched/walt.c",
        "target": "kernel/sched/walt/walt.c split layout",
        "action": "Map package runtime accounting around walt_update_task_ravg/update_cpu_busy_time by semantics, preserving Lisa event/window ordering.",
        "risk": "high",
    },
    {
        "area": "cpuset",
        "donor": "cpuset_fork minor-task cpus_allowed override",
        "target": "Lisa cpuset fork/attach/allowed-mask semantic equivalent",
        "action": "Locate exact Lisa fork inheritance path before insertion; do not force affinity globally.",
        "risk": "high",
    },
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def require(root: Path, table: dict[str, tuple[str, ...]], prefix: str, failures: list[str]) -> dict:
    out = {}
    for rel, markers in table.items():
        p = root / rel
        row = {"exists": p.is_file(), "markers": {}}
        if not p.is_file():
            failures.append(f"{prefix}_MISSING_FILE:{rel}")
            out[rel] = row
            continue
        body = read(p)
        for marker in markers:
            ok = marker in body
            row["markers"][marker] = ok
            if not ok:
                failures.append(f"{prefix}_MISSING_MARKER:{rel}:{marker}")
        out[rel] = row
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=Path, required=True)
    ap.add_argument("--donor", type=Path, required=True)
    ap.add_argument("--json", type=Path, required=True)
    ap.add_argument("--text", type=Path, required=True)
    args = ap.parse_args()

    failures: list[str] = []
    donor = require(args.donor, DONOR_HOOKS, "DONOR", failures)
    target = require(args.target, TARGET_LANDMARKS, "TARGET", failures)

    target_flat_walt = (args.target / "kernel/sched/walt.c").is_file()
    target_split_walt = (args.target / "kernel/sched/walt/walt.c").is_file()
    donor_flat_walt = (args.donor / "kernel/sched/walt.c").is_file()
    donor_split_walt = (args.donor / "kernel/sched/walt/walt.c").is_file()

    if target_flat_walt or not target_split_walt:
        failures.append("TARGET_WALT_LAYOUT_UNEXPECTED")
    if not donor_flat_walt or donor_split_walt:
        failures.append("DONOR_WALT_LAYOUT_UNEXPECTED")

    target_absent = {}
    for rel in MUST_NOT_EXIST_TARGET:
        present = (args.target / rel).is_file()
        target_absent[rel] = not present
        if present:
            failures.append(f"TARGET_BASELINE_ALREADY_HAS_PORT_FILE:{rel}")

    report = {
        "candidate": "0059",
        "target_ref": TARGET_REF,
        "donor_repo": DONOR_REPO,
        "donor_ref": DONOR_REF,
        "result": "PASS" if not failures else "FAIL",
        "donor_hook_evidence": donor,
        "target_landing_landmarks": target,
        "target_walt_layout": {"flat": target_flat_walt, "split": target_split_walt},
        "donor_walt_layout": {"flat": donor_flat_walt, "split": donor_split_walt},
        "raw_donor_patch_allowed": False,
        "target_port_files_absent": target_absent,
        "semantic_port_plan": PORT_PLAN,
        "failures": failures,
        "claims": {
            "source_mutated": False,
            "kernel_compiled": False,
            "runtime_tested": False,
            "jank_fixed": False,
        },
    }
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    lines = [
        f"CANDIDATE0059_SEMANTIC_HOOK_MAP={report['result']}",
        f"TARGET_REF={TARGET_REF}",
        f"DONOR={DONOR_REPO}@{DONOR_REF}",
        "TARGET_WALT_LAYOUT=split",
        "DONOR_WALT_LAYOUT=flat",
        "RAW_DONOR_PATCH_ALLOWED=false",
        "KABI_POLICY=use-reserve-mechanism-before-adding-package-runtime-state",
    ]
    for item in PORT_PLAN:
        lines.append(
            "MAP=" + item["area"] + "|" + item["risk"] + "|" + item["action"]
        )
    if failures:
        lines.extend("FAILURE=" + x for x in failures)
    else:
        lines.append("NEXT=generate bounded stage-1 port patch only after KABI reserve sizing and exact lifecycle hook review")
    args.text.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
