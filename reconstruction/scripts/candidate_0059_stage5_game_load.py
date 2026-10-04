#!/usr/bin/env python3
"""Candidate0059 Stage5 bounded GLK/game-load accounting layer.

Requires Stages1-4. This stage restores the stock-lineage glk.c source landing
and exact game_load_init identity, but only as passive per-CPU runtime/history
accounting. It deliberately does NOT implement GLK frequency policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TARGET_REF = "6e568aabc77a06fa787baec1d9e60e4b559874a3"
DONOR_REF = "LeviMarvin/android_kernel_xiaomi_alioth@e7065bc9ead4a0ca183f51101e07dd45a9d5c558"

GLK_C = r'''// SPDX-License-Identifier: GPL-2.0-only
/*
 * Candidate0059 Stage5: bounded passive game-load accounting.
 *
 * This restores the stock-lineage game_load_* API and game_load_init identity
 * without applying cpufreq limits, boosts, thermal changes, or device ioctls.
 */
#include <linux/init.h>
#include <linux/module.h>
#include <linux/percpu.h>
#include <linux/pkg_stat.h>
#include <linux/sched.h>
#include <linux/spinlock.h>

#define C0059_GAME_HISTORY_ITEMS 8

struct c0059_game_load_cpu {
	raw_spinlock_t lock;
	u64 total_runtime;
	u64 history[C0059_GAME_HISTORY_ITEMS];
};

static DEFINE_PER_CPU(struct c0059_game_load_cpu, c0059_game_load);
static unsigned int game_history_slot;
static bool game_load_ready;

void game_load_update(struct task_struct *task, u64 delta, int cpu)
{
	struct c0059_game_load_cpu *load;
	unsigned long flags;

	if (!READ_ONCE(game_load_ready) || !task || !delta)
		return;
	if (cpu < 0 || cpu >= nr_cpu_ids)
		return;

	load = per_cpu_ptr(&c0059_game_load, cpu);
	raw_spin_lock_irqsave(&load->lock, flags);
	load->total_runtime += delta;
	raw_spin_unlock_irqrestore(&load->lock, flags);
}

void game_load_history_update(u64 tick)
{
	unsigned int slot;
	int cpu;

	(void)tick;
	if (!READ_ONCE(game_load_ready))
		return;

	slot = (READ_ONCE(game_history_slot) + 1) % C0059_GAME_HISTORY_ITEMS;
	for_each_possible_cpu(cpu) {
		struct c0059_game_load_cpu *load = per_cpu_ptr(&c0059_game_load, cpu);
		unsigned long flags;

		raw_spin_lock_irqsave(&load->lock, flags);
		load->history[slot] = load->total_runtime;
		raw_spin_unlock_irqrestore(&load->lock, flags);
	}
	WRITE_ONCE(game_history_slot, slot);
}

void game_load_reset(void)
{
	int cpu;

	for_each_possible_cpu(cpu) {
		struct c0059_game_load_cpu *load = per_cpu_ptr(&c0059_game_load, cpu);
		unsigned long flags;

		raw_spin_lock_irqsave(&load->lock, flags);
		load->total_runtime = 0;
		memset(load->history, 0, sizeof(load->history));
		raw_spin_unlock_irqrestore(&load->lock, flags);
	}
	WRITE_ONCE(game_history_slot, 0);
}

int game_load_init(void)
{
	int cpu;

	for_each_possible_cpu(cpu) {
		struct c0059_game_load_cpu *load = per_cpu_ptr(&c0059_game_load, cpu);

		raw_spin_lock_init(&load->lock);
		load->total_runtime = 0;
		memset(load->history, 0, sizeof(load->history));
	}
	WRITE_ONCE(game_history_slot, 0);
	WRITE_ONCE(game_load_ready, true);
	pr_info("Candidate0059 passive game-load accounting enabled\n");
	return 0;
}
late_initcall(game_load_init);
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
    if not (root / "kernel/sched/migt_sched.c").is_file():
        raise RuntimeError("Stage4 migt_sched.c missing")
    if "module_init(migt_sched_init);" not in (root / "kernel/sched/migt_sched.c").read_text():
        raise RuntimeError("Stage4 stock-lineage migt_sched_init registration missing")

    glk = root / "kernel/sched/glk.c"
    if glk.exists():
        raise RuntimeError("Stage5 glk.c already exists")
    glk.write_text(GLK_C)

    makefile = root / "kernel/sched/Makefile"
    insert_after(
        makefile,
        "obj-$(CONFIG_MIGT) += migt_sched.o\n",
        "obj-$(CONFIG_PACKAGE_RUNTIME_INFO) += glk.o\n",
    )

    pkg_h = root / "include/linux/pkg_stat.h"
    insert_after(
        pkg_h,
        "void migt_hook(struct task_struct *task, u64 delta, int cpu);\n",
        "void game_load_update(struct task_struct *task, u64 delta, int cpu);\n"
        "void game_load_history_update(u64 tick);\n"
        "void game_load_reset(void);\n"
        "int game_load_init(void);\n",
    )
    insert_after(
        pkg_h,
        "static inline void migt_hook(struct task_struct *task, u64 delta, int cpu) { }\n",
        "static inline void game_load_update(struct task_struct *task, u64 delta, int cpu) { }\n"
        "static inline void game_load_history_update(u64 tick) { }\n"
        "static inline void game_load_reset(void) { }\n"
        "static inline int game_load_init(void) { return 0; }\n",
    )

def verify(root: Path) -> dict:
    failures: list[str] = []
    checks = {
        "kernel/sched/glk.c": (
            "void game_load_update(",
            "void game_load_history_update(",
            "void game_load_reset(void)",
            "int game_load_init(void)",
            "late_initcall(game_load_init);",
            "DEFINE_PER_CPU",
        ),
        "kernel/sched/Makefile": (
            "obj-$(CONFIG_PACKAGE_RUNTIME_INFO) += glk.o",
        ),
        "include/linux/pkg_stat.h": (
            "void game_load_update(",
            "void game_load_history_update(",
            "void game_load_reset(void);",
            "int game_load_init(void);",
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

    body = (root / "kernel/sched/glk.c").read_text() if (root / "kernel/sched/glk.c").is_file() else ""
    forbidden = (
        "cpufreq_update_policy",
        "cpufreq_verify_within_limits",
        "glk_freq_limit(",
        "glk_cal_freq(",
        "core_ctl_set_boost",
        "set_cpus_allowed_ptr",
        "/dev/migt",
        "/dev/metis",
        "iorap_dev",
        "misc_register",
        "unlocked_ioctl",
    )
    for token in forbidden:
        if token in body:
            failures.append("FORBIDDEN_STAGE5_FEATURE:" + token)

    return {
        "candidate": "0059",
        "stage": "bounded-passive-game-load",
        "target_ref": TARGET_REF,
        "donor_reference": DONOR_REF,
        "result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "claims": {
            "game_load_source_present": True,
            "game_load_policy_active": False,
            "glk_frequency_policy_ported": False,
            "device_migt_driver_ported": False,
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

    print("CANDIDATE0059_STAGE5=" + report["result"])
    print("GAME_LOAD_SOURCE_PRESENT=true")
    print("GLK_FREQUENCY_POLICY_PORTED=false")
    print("DEVICE_MIGT_DRIVER_PORTED=false")
    print("RUNTIME_TESTED=false")
    for item in report["failures"]:
        print("FAILURE=" + item)
    return 0 if report["result"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
