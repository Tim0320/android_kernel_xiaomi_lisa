#!/usr/bin/env python3
"""Candidate0059 Stage3 active package-runtime accounting core.

Requires Stage1 and Stage2 to be applied first. Stage3 replaces the weak/no-op
accounting bridge with a bounded stock-lineage package runtime core while still
leaving MIGT boost/ioctl, GLK, cpuset overrides, Metis and iorap untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TARGET_REF = "6e568aabc77a06fa787baec1d9e60e4b559874a3"

PKG_CORE_C = r'''// SPDX-License-Identifier: GPL-2.0-only
/*
 * Candidate0059 Stage3: bounded Xiaomi package-runtime accounting core.
 *
 * This activates task/user cluster runtime accounting through the Stage2
 * split-WALT hooks. MIGT is still a weak hook in this stage.
 */
#include <linux/compiler.h>
#include <linux/init.h>
#include <linux/jiffies.h>
#include <linux/pkg_stat.h>
#include <linux/sched.h>
#include <linux/spinlock.h>
#include <linux/topology.h>

static bool pkg_runtime_enabled;
static enum cluster_type pkg_cpu_cluster[NR_CPUS];
static DEFINE_RAW_SPINLOCK(pkg_cluster_lock);
static bool pkg_cluster_ready;
static unsigned int pkg_runtime_window_secs = 300;
static unsigned int pkg_history_slot;
static u64 pkg_last_roll_jiffies;

void __weak migt_hook(struct task_struct *task, u64 delta, int cpu)
{
}

static void pkg_build_cluster_map(void)
{
	unsigned long flags;
	unsigned long caps[CLUSTER_TYPES] = { 0 };
	int cap_count = 0;
	int cpu, i, j;

	if (READ_ONCE(pkg_cluster_ready))
		return;

	raw_spin_lock_irqsave(&pkg_cluster_lock, flags);
	if (pkg_cluster_ready)
		goto out;

	for_each_possible_cpu(cpu) {
		unsigned long cap = arch_scale_cpu_capacity(cpu);
		bool found = false;

		for (i = 0; i < cap_count; i++) {
			if (caps[i] == cap) {
				found = true;
				break;
			}
		}
		if (found)
			continue;

		if (cap_count < CLUSTER_TYPES) {
			caps[cap_count++] = cap;
			for (i = cap_count - 1; i > 0 && caps[i] < caps[i - 1]; i--) {
				unsigned long tmp = caps[i];
				caps[i] = caps[i - 1];
				caps[i - 1] = tmp;
			}
		}
	}

	for_each_possible_cpu(cpu) {
		unsigned long cap = arch_scale_cpu_capacity(cpu);
		enum cluster_type type = LITTLE_CLUSTER;

		for (j = 0; j < cap_count; j++) {
			if (cap == caps[j]) {
				if (cap_count <= CLUSTER_TYPES)
					type = (enum cluster_type)j;
				break;
			}
		}
		if (type >= CLUSTER_TYPES)
			type = BIG_CLUSTER;
		pkg_cpu_cluster[cpu] = type;
	}

	WRITE_ONCE(pkg_cluster_ready, true);
out:
	raw_spin_unlock_irqrestore(&pkg_cluster_lock, flags);
}

static enum cluster_type pkg_cluster_type(int cpu)
{
	if (unlikely(cpu < 0 || cpu >= nr_cpu_ids))
		return LITTLE_CLUSTER;
	if (unlikely(!READ_ONCE(pkg_cluster_ready)))
		pkg_build_cluster_map();
	if (pkg_cpu_cluster[cpu] >= CLUSTER_TYPES)
		return LITTLE_CLUSTER;
	return pkg_cpu_cluster[cpu];
}

bool pkg_enable(void)
{
	return READ_ONCE(pkg_runtime_enabled);
}

void update_pkg_load(struct task_struct *task, int cpu, int flag,
		     u64 wallclock, u64 delta)
{
	struct package_runtime_info *task_state;
	struct package_runtime_info *user_state;
	struct user_struct *user;
	enum cluster_type cluster;
	unsigned int slot;

	if (!pkg_enable() || !task || !delta || is_idle_task(task))
		return;

	task_state = pkg_task_state(task);
	if (!task_state)
		return;

	user = READ_ONCE(task_state->owner_user);
	if (!user || !user_pkg(user->uid.val))
		return;

	user_state = pkg_user_state(user);
	if (!user_state)
		return;

	cluster = pkg_cluster_type(cpu);
	slot = READ_ONCE(pkg_history_slot) % HISTORY_ITMES;

	if (READ_ONCE(user_state->edt) == FRONT) {
		task_state->front_runtime[HISTORY_ITMES][cluster] += delta;
		task_state->front_runtime[slot][cluster] =
			task_state->front_runtime[HISTORY_ITMES][cluster];
		user_state->front_runtime[HISTORY_ITMES][cluster] += delta;
		user_state->front_runtime[slot][cluster] =
			user_state->front_runtime[HISTORY_ITMES][cluster];
	} else {
		task_state->back_runtime[HISTORY_ITMES][cluster] += delta;
		task_state->back_runtime[slot][cluster] =
			task_state->back_runtime[HISTORY_ITMES][cluster];
		user_state->back_runtime[HISTORY_ITMES][cluster] += delta;
		user_state->back_runtime[slot][cluster] =
			user_state->back_runtime[HISTORY_ITMES][cluster];
	}

	switch (cluster) {
	case BIG_CLUSTER:
		task_state->sup_cluster_runtime[HISTORY_ITMES] += delta;
		user_state->sup_cluster_runtime[HISTORY_ITMES] += delta;
		break;
	case MID_CLUSTER:
		task_state->big_cluster_runtime[HISTORY_ITMES] += delta;
		user_state->big_cluster_runtime[HISTORY_ITMES] += delta;
		break;
	case LITTLE_CLUSTER:
	default:
		task_state->little_cluster_runtime[HISTORY_ITMES] += delta;
		user_state->little_cluster_runtime[HISTORY_ITMES] += delta;
		break;
	}

	task_state->sup_cluster_runtime[slot] =
		task_state->sup_cluster_runtime[HISTORY_ITMES];
	task_state->big_cluster_runtime[slot] =
		task_state->big_cluster_runtime[HISTORY_ITMES];
	task_state->little_cluster_runtime[slot] =
		task_state->little_cluster_runtime[HISTORY_ITMES];
	user_state->sup_cluster_runtime[slot] =
		user_state->sup_cluster_runtime[HISTORY_ITMES];
	user_state->big_cluster_runtime[slot] =
		user_state->big_cluster_runtime[HISTORY_ITMES];
	user_state->little_cluster_runtime[slot] =
		user_state->little_cluster_runtime[HISTORY_ITMES];

	migt_hook(task, delta, cpu);
}

void package_runtime_monitor(u64 now)
{
	u64 window;

	if (!pkg_enable())
		return;

	window = (u64)READ_ONCE(pkg_runtime_window_secs) * HZ;
	if (now - READ_ONCE(pkg_last_roll_jiffies) < window)
		return;

	WRITE_ONCE(pkg_last_roll_jiffies, now);
	WRITE_ONCE(pkg_history_slot,
		   (READ_ONCE(pkg_history_slot) + 1) % HISTORY_ITMES);
}

static int __init pkg_runtime_core_init(void)
{
	pkg_build_cluster_map();
	WRITE_ONCE(pkg_history_slot, 0);
	WRITE_ONCE(pkg_last_roll_jiffies, get_jiffies_64());
	WRITE_ONCE(pkg_runtime_enabled, true);
	pr_info("Candidate0059 package runtime accounting core enabled\n");
	return 0;
}
late_initcall(pkg_runtime_core_init);
'''

def replace_once(path: Path, old: str, new: str) -> None:
    body = path.read_text()
    count = body.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement, found {count}: {old!r}")
    path.write_text(body.replace(old, new, 1))

def apply(root: Path) -> None:
    if not (root / "kernel/sched/pkg_state.c").is_file():
        raise RuntimeError("Stage1 missing")
    if not (root / "kernel/sched/pkg_bridge.c").is_file():
        raise RuntimeError("Stage2 missing")
    if "pkg_task_bind_user" not in (root / "include/linux/pkg_stat.h").read_text():
        raise RuntimeError("Stage2 header bridge missing")

    core = root / "kernel/sched/pkg_core.c"
    if core.exists():
        raise RuntimeError("Stage3 pkg_core.c already exists")
    core.write_text(PKG_CORE_C)

    makefile = root / "kernel/sched/Makefile"
    replace_once(
        makefile,
        "obj-$(CONFIG_PACKAGE_RUNTIME_INFO) += pkg_bridge.o\n",
        "obj-$(CONFIG_PACKAGE_RUNTIME_INFO) += pkg_bridge.o\n"
        "obj-$(CONFIG_PACKAGE_RUNTIME_INFO) += pkg_core.o\n",
    )

def verify(root: Path) -> dict:
    failures: list[str] = []
    checks = {
        "kernel/sched/pkg_core.c": (
            "bool pkg_enable(void)",
            "void update_pkg_load(",
            "void package_runtime_monitor(",
            "void __weak migt_hook(",
            "arch_scale_cpu_capacity",
            "late_initcall(pkg_runtime_core_init);",
        ),
        "kernel/sched/Makefile": (
            "obj-$(CONFIG_PACKAGE_RUNTIME_INFO) += pkg_core.o",
        ),
        "kernel/sched/pkg_bridge.c": (
            "bool __weak pkg_enable(void)",
            "void __weak update_pkg_load(",
        ),
    }
    evidence = {}
    for rel, markers in checks.items():
        path = root / rel
        body = path.read_text() if path.is_file() else ""
        evidence[rel] = {
            "exists": path.is_file(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        }
        if not path.is_file():
            failures.append("MISSING_FILE:" + rel)
            continue
        for marker in markers:
            if marker not in body:
                failures.append("MISSING_MARKER:" + rel + ":" + marker)

    body = (root / "kernel/sched/pkg_core.c").read_text() if (root / "kernel/sched/pkg_core.c").is_file() else ""
    for forbidden in ("/dev/migt", "/dev/metis", "misc_register", "iorap_dev",
                      "cpufreq_update_policy", "core_ctl_set_boost"):
        if forbidden in body:
            failures.append("FORBIDDEN_STAGE3_FEATURE:" + forbidden)

    return {
        "candidate": "0059",
        "stage": "active-package-runtime-accounting",
        "target_ref": TARGET_REF,
        "result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "files": evidence,
        "claims": {
            "runtime_accounting_source_active": True,
            "full_migt_ported": False,
            "migt_ioctl_exposed": False,
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

    print("CANDIDATE0059_STAGE3=" + report["result"])
    print("RUNTIME_ACCOUNTING_SOURCE_ACTIVE=true")
    print("FULL_MIGT_PORTED=false")
    print("MIGT_IOCTL_EXPOSED=false")
    print("RUNTIME_TESTED=false")
    for item in report["failures"]:
        print("FAILURE=" + item)
    return 0 if report["result"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
