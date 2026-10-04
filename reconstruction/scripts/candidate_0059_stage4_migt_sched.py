#!/usr/bin/env python3
"""Candidate0059 Stage4 bounded MIGT scheduler/statistics layer.

Requires Stage1+Stage2+Stage3. This stage restores the stock-lineage MIGT
scheduler landing point and CONFIG_MIGT without exposing /dev/migt, Metis,
frequency forcing, cpuset overrides, thermal changes, or iorap shims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TARGET_REF = "6e568aabc77a06fa787baec1d9e60e4b559874a3"
DONOR_REF = "LeviMarvin/android_kernel_xiaomi_alioth@e7065bc9ead4a0ca183f51101e07dd45a9d5c558"

MIGT_KCONFIG = r'''config MIGT
	bool "Mi Game Turbo scheduler statistics"
	depends on MIHW && PACKAGE_RUNTIME_INFO
	default n
	help
	  Restore the stock-lineage MIGT scheduler/statistics landing point for
	  Candidate0059. This stage does not expose device ioctls or force CPU
	  frequency/thermal policy.

'''

MIGT_SCHED_C = r'''// SPDX-License-Identifier: GPL-2.0-only
/*
 * Candidate0059 Stage4: bounded MIGT scheduler/statistics layer.
 *
 * The original Xiaomi chain feeds migt_hook() from package runtime accounting.
 * This stage restores that strong scheduler-side hook against the ABI-safe
 * pointer-backed state built in Stages1-3. Device-facing MIGT control remains
 * deliberately absent.
 */
#include <linux/compiler.h>
#include <linux/cred.h>
#include <linux/init.h>
#include <linux/pkg_stat.h>
#include <linux/sched.h>
#include <linux/user_namespace.h>

static bool migt_sched_ready;

static inline u32 migt_u64_to_u32_sat(u64 value)
{
	return value > (u64)~0U ? ~0U : (u32)value;
}

void migt_monitor_init(struct task_struct *task)
{
	struct package_runtime_info *state;
	int i;

	if (!task)
		return;

	state = pkg_task_state(task);
	if (!state)
		return;

	state->migt.migt_count = 0;
	state->migt.prev_sum = 0;
	state->migt.max_exec = 0;
	state->migt.fps_exec = 0;
	state->migt.fps_mexec = 0;
	state->migt.flag = MIGT_NORMAL_TASK;
	state->migt.run_times = 0;
	state->migt.wake_render = 0;
	state->migt.boost_end = 0;
	cpumask_copy(&state->migt.cpus_allowed, cpu_possible_mask);
	for (i = 0; i < NUM_MIGT_BUCKETS; i++)
		state->migt.bucket[i] = 0;
}

void migt_monitor_hook(int enqueue, int cpu, struct task_struct *task,
		       u64 walltime)
{
	struct package_runtime_info *state;
	u64 exec_delta;
	u32 sample;

	(void)cpu;
	(void)walltime;

	if (!READ_ONCE(migt_sched_ready) || !task)
		return;

	state = pkg_task_state(task);
	if (!state)
		return;

	if (enqueue) {
		state->migt.prev_sum = task->se.sum_exec_runtime;
		return;
	}

	if (task->se.sum_exec_runtime < state->migt.prev_sum)
		return;

	exec_delta = task->se.sum_exec_runtime - state->migt.prev_sum;
	sample = migt_u64_to_u32_sat(exec_delta);
	if (sample > state->migt.max_exec)
		state->migt.max_exec = sample;
}

void migt_hook(struct task_struct *task, u64 delta, int cpu)
{
	struct package_runtime_info *state;
	uid_t uid;
	u32 sample;

	(void)cpu;

	if (!READ_ONCE(migt_sched_ready) || !task || !delta)
		return;

	uid = from_kuid(&init_user_ns, task_uid(task));
	if (!user_pkg(uid))
		return;

	state = pkg_task_state(task);
	if (!state)
		return;

	state->migt.run_times += delta;
	state->migt.fps_exec += delta;
	sample = migt_u64_to_u32_sat(delta);
	if (sample > state->migt.max_exec)
		state->migt.max_exec = sample;
}

static int __init migt_sched_init(void)
{
	WRITE_ONCE(migt_sched_ready, true);
	pr_info("Candidate0059 MIGT scheduler statistics enabled\n");
	return 0;
}
late_initcall(migt_sched_init);
'''

def replace_once(path: Path, old: str, new: str) -> None:
    body = path.read_text()
    count = body.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement, found {count}: {old!r}")
    path.write_text(body.replace(old, new, 1))

def insert_after(path: Path, anchor: str, addition: str) -> None:
    replace_once(path, anchor, anchor + addition)

def apply(root: Path) -> None:
    if not (root / "kernel/sched/pkg_core.c").is_file():
        raise RuntimeError("Stage3 pkg_core.c missing")
    if "bool pkg_enable(void)" not in (root / "kernel/sched/pkg_core.c").read_text():
        raise RuntimeError("Stage3 active accounting missing")

    sched = root / "kernel/sched/migt_sched.c"
    if sched.exists():
        raise RuntimeError("Stage4 migt_sched.c already exists")
    sched.write_text(MIGT_SCHED_C)

    kconfig = root / "drivers/mihw/Kconfig"
    if "config MIGT" in kconfig.read_text():
        raise RuntimeError("CONFIG_MIGT already declared")
    kconfig.write_text(MIGT_KCONFIG + kconfig.read_text())

    makefile = root / "kernel/sched/Makefile"
    insert_after(
        makefile,
        "obj-$(CONFIG_PACKAGE_RUNTIME_INFO) += pkg_core.o\n",
        "obj-$(CONFIG_MIGT) += migt_sched.o\n",
    )

    pkg_h = root / "include/linux/pkg_stat.h"
    insert_after(
        pkg_h,
        "void package_runtime_monitor(u64 now);\n",
        "void migt_monitor_init(struct task_struct *task);\n"
        "void migt_monitor_hook(int enqueue, int cpu, struct task_struct *task, u64 walltime);\n"
        "void migt_hook(struct task_struct *task, u64 delta, int cpu);\n",
    )
    insert_after(
        pkg_h,
        "static inline void package_runtime_monitor(u64 now) { }\n",
        "static inline void migt_monitor_init(struct task_struct *task) { }\n"
        "static inline void migt_monitor_hook(int enqueue, int cpu, struct task_struct *task, u64 walltime) { }\n"
        "static inline void migt_hook(struct task_struct *task, u64 delta, int cpu) { }\n",
    )

def verify(root: Path) -> dict:
    failures: list[str] = []
    checks = {
        "drivers/mihw/Kconfig": (
            "config MIGT",
            "depends on MIHW && PACKAGE_RUNTIME_INFO",
        ),
        "kernel/sched/Makefile": (
            "obj-$(CONFIG_MIGT) += migt_sched.o",
        ),
        "kernel/sched/migt_sched.c": (
            "void migt_monitor_init(",
            "void migt_monitor_hook(",
            "void migt_hook(",
            "migt_sched_init",
            "late_initcall(migt_sched_init);",
            "state->migt.run_times += delta;",
        ),
        "include/linux/pkg_stat.h": (
            "void migt_monitor_init(",
            "void migt_monitor_hook(",
            "void migt_hook(",
        ),
        "kernel/sched/pkg_core.c": (
            "migt_hook(task, delta, cpu);",
        ),
    }
    evidence = {}
    for rel, markers in checks.items():
        p = root / rel
        body = p.read_text() if p.is_file() else ""
        evidence[rel] = {
            "exists": p.is_file(),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
        }
        if not p.is_file():
            failures.append("MISSING_FILE:" + rel)
            continue
        for marker in markers:
            if marker not in body:
                failures.append("MISSING_MARKER:" + rel + ":" + marker)

    joined = "\n".join(
        (root / p).read_text()
        for p in ("kernel/sched/migt_sched.c", "include/linux/pkg_stat.h")
        if (root / p).is_file()
    )
    for forbidden in (
        "/dev/migt",
        "/dev/metis",
        "misc_register",
        "unlocked_ioctl",
        "iorap_dev",
        "cpufreq_update_policy",
        "core_ctl_set_boost",
        "set_cpus_allowed_ptr",
    ):
        if forbidden in joined:
            failures.append("FORBIDDEN_STAGE4_FEATURE:" + forbidden)

    return {
        "candidate": "0059",
        "stage": "bounded-migt-scheduler-statistics",
        "target_ref": TARGET_REF,
        "donor_reference": DONOR_REF,
        "result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "claims": {
            "migt_scheduler_statistics_source_active": True,
            "device_facing_migt_driver_ported": False,
            "migt_ioctl_exposed": False,
            "metis_compatibility_added": False,
            "runtime_tested": False,
            "jank_fixed": False,
        },
    }

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("apply", "verify"))
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    root = args.source.resolve()

    if args.mode == "apply":
        apply(root)
    report = verify(root)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print("CANDIDATE0059_STAGE4=" + report["result"])
    print("MIGT_SCHEDULER_STATISTICS_SOURCE_ACTIVE=true")
    print("DEVICE_MIGT_DRIVER_PORTED=false")
    print("MIGT_IOCTL_EXPOSED=false")
    print("METIS_COMPAT_ADDED=false")
    print("RUNTIME_TESTED=false")
    for item in report["failures"]:
        print("FAILURE=" + item)
    return 0 if report["result"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
