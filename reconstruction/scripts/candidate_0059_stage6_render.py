#!/usr/bin/env python3
"""Candidate0059 Stage6 pointer-backed MIGT render tracking.

Requires Stages1-5. Restores the stock-lineage render queue/dequeue state used
by legacy MIGT ioctls, without creating /dev/migt or applying boost policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TARGET_REF = "6e568aabc77a06fa787baec1d9e60e4b559874a3"
DONOR_REF = "LeviMarvin/android_kernel_xiaomi_alioth@e7065bc9ead4a0ca183f51101e07dd45a9d5c558"

MIGT_RENDER_C = r'''// SPDX-License-Identifier: GPL-2.0-only
/*
 * Candidate0059 Stage6: ABI-safe MIGT render tracking.
 *
 * This mirrors the stock-lineage QRENDER/DQRENDER state machine while using
 * pkg_task_state() instead of embedding Xiaomi state directly in task_struct.
 */
#include <linux/jiffies.h>
#include <linux/pkg_stat.h>
#include <linux/rcupdate.h>
#include <linux/sched.h>
#include <linux/sched/signal.h>
#include <linux/seqlock.h>
#include <linux/spinlock.h>
#include <linux/string.h>

struct c0059_render_info {
	seqcount_t seq;
	raw_spinlock_t lock;
	bool active;
	int pid;
	unsigned long last_update_jiffies;
	char comm[TASK_COMM_LEN];
};

static struct c0059_render_info render_info[RENDER_TYPES];

static void set_render_flag(struct task_struct *task, enum RENDER_TYPE type)
{
	struct package_runtime_info *state = pkg_task_state(task);

	if (!state || type < 0 || type >= RENDER_TYPES)
		return;
	state->migt.flag |= 1U << (GAME_QRENDER_TASK + type);
}

static void clean_render_flag(struct task_struct *task, enum RENDER_TYPE type)
{
	struct package_runtime_info *state = pkg_task_state(task);

	if (!state || type < 0 || type >= RENDER_TYPES)
		return;
	state->migt.flag &= ~(1U << (GAME_QRENDER_TASK + type));
}

void migt_render_state_init(void)
{
	int type;

	for (type = 0; type < RENDER_TYPES; type++) {
		seqcount_init(&render_info[type].seq);
		raw_spin_lock_init(&render_info[type].lock);
		render_info[type].active = false;
		render_info[type].pid = -1;
		render_info[type].last_update_jiffies = 0;
		memset(render_info[type].comm, 0, sizeof(render_info[type].comm));
	}
}

void reset_render_info(enum RENDER_TYPE type)
{
	struct task_struct *task;
	int old_pid;

	if (type < 0 || type >= RENDER_TYPES)
		return;

	raw_spin_lock(&render_info[type].lock);
	write_seqcount_begin(&render_info[type].seq);
	old_pid = render_info[type].pid;
	render_info[type].active = false;
	render_info[type].pid = -1;
	render_info[type].last_update_jiffies = 0;
	memset(render_info[type].comm, 0, sizeof(render_info[type].comm));
	write_seqcount_end(&render_info[type].seq);
	raw_spin_unlock(&render_info[type].lock);

	if (old_pid <= 0)
		return;

	rcu_read_lock();
	task = find_task_by_vpid(old_pid);
	if (task)
		clean_render_flag(task, type);
	rcu_read_unlock();
}

void update_render_info(struct task_struct *task, enum RENDER_TYPE type)
{
	struct task_struct *old_task;
	int old_pid;

	if (!task || type < 0 || type >= RENDER_TYPES)
		return;

	raw_spin_lock(&render_info[type].lock);
	write_seqcount_begin(&render_info[type].seq);
	if (render_info[type].pid == task->pid) {
		write_seqcount_end(&render_info[type].seq);
		raw_spin_unlock(&render_info[type].lock);
		return;
	}

	old_pid = render_info[type].pid;
	render_info[type].active = true;
	render_info[type].pid = task->pid;
	render_info[type].last_update_jiffies = jiffies;
	strlcpy(render_info[type].comm, task->comm, sizeof(render_info[type].comm));
	set_render_flag(task, type);
	write_seqcount_end(&render_info[type].seq);
	raw_spin_unlock(&render_info[type].lock);

	if (old_pid <= 0)
		return;

	rcu_read_lock();
	old_task = find_task_by_vpid(old_pid);
	if (old_task)
		clean_render_flag(old_task, type);
	rcu_read_unlock();
}

int is_render_thread(struct task_struct *task)
{
	struct package_runtime_info *state;

	if (!task)
		return 0;
	state = pkg_task_state(task);
	if (!state)
		return 0;
	return !!(state->migt.flag & MASK_RTASK);
}
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
    if not (root / "kernel/sched/glk.c").is_file():
        raise RuntimeError("Stage5 glk.c missing")
    if not (root / "kernel/sched/migt_sched.c").is_file():
        raise RuntimeError("Stage4 migt_sched.c missing")

    render = root / "kernel/sched/migt_render.c"
    if render.exists():
        raise RuntimeError("Stage6 migt_render.c already exists")
    render.write_text(MIGT_RENDER_C)

    pkg_h = root / "include/linux/pkg_stat.h"
    replace_once(
        pkg_h,
        "#define MINOR_TASK (1U << MIGT_MINOR_TASK)\n",
        "enum RENDER_TYPE {\n"
        "\tRENDER_QUEUE_THREAD = 0,\n"
        "\tRENDER_DEQUEUE_THREAD,\n"
        "\tRENDER_TYPES,\n"
        "};\n\n"
        "#define MASK_MI_VTASK (1U << MI_VIP_TASK)\n"
        "#define MASK_STASK (1U << GAME_SUPER_TASK)\n"
        "#define MASK_RTASK ((1U << GAME_QRENDER_TASK) | (1U << GAME_DQRENDER_TASK))\n"
        "#define MASK_VTASK (MASK_STASK | MASK_RTASK | (1U << GAME_VIP_TASK))\n"
        "#define MASK_ITASK (MASK_VTASK | (1U << GAME_IP_TASK))\n"
        "#define MASK_GTASK (MASK_ITASK | (1U << GAME_NORMAL_TASK))\n"
        "#define MASK_CLE_GTASK (~MASK_GTASK)\n"
        "#define MINOR_TASK (1U << MIGT_MINOR_TASK)\n",
    )

    insert_after(
        pkg_h,
        "void migt_hook(struct task_struct *task, u64 delta, int cpu);\n",
        "void migt_render_state_init(void);\n"
        "void reset_render_info(enum RENDER_TYPE type);\n"
        "void update_render_info(struct task_struct *task, enum RENDER_TYPE type);\n"
        "int is_render_thread(struct task_struct *task);\n",
    )
    insert_after(
        pkg_h,
        "static inline void migt_hook(struct task_struct *task, u64 delta, int cpu) { }\n",
        "static inline void migt_render_state_init(void) { }\n"
        "static inline void reset_render_info(enum RENDER_TYPE type) { }\n"
        "static inline void update_render_info(struct task_struct *task, enum RENDER_TYPE type) { }\n"
        "static inline int is_render_thread(struct task_struct *task) { return 0; }\n",
    )

    makefile = root / "kernel/sched/Makefile"
    insert_after(
        makefile,
        "obj-$(CONFIG_MIGT) += migt_sched.o\n",
        "obj-$(CONFIG_MIGT) += migt_render.o\n",
    )

    sched = root / "kernel/sched/migt_sched.c"
    insert_after(
        sched,
        "static int __init migt_sched_init(void)\n{\n",
        "\tmigt_render_state_init();\n",
    )

def verify(root: Path) -> dict:
    failures: list[str] = []
    checks = {
        "include/linux/pkg_stat.h": (
            "enum RENDER_TYPE",
            "RENDER_QUEUE_THREAD = 0",
            "RENDER_DEQUEUE_THREAD",
            "#define MASK_RTASK",
            "void update_render_info(",
            "void reset_render_info(",
            "int is_render_thread(",
        ),
        "kernel/sched/Makefile": (
            "obj-$(CONFIG_MIGT) += migt_render.o",
        ),
        "kernel/sched/migt_render.c": (
            "void migt_render_state_init(void)",
            "void reset_render_info(",
            "void update_render_info(",
            "int is_render_thread(",
            "pkg_task_state(task)",
            "find_task_by_vpid",
        ),
        "kernel/sched/migt_sched.c": (
            "migt_render_state_init();",
            "module_init(migt_sched_init);",
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

    body = (root / "kernel/sched/migt_render.c").read_text() if (root / "kernel/sched/migt_render.c").is_file() else ""
    for token in (
        "misc_register",
        "unlocked_ioctl",
        "/dev/migt",
        "/dev/metis",
        "cpufreq_update_policy",
        "core_ctl_set_boost",
        "set_cpus_allowed_ptr",
        "iorap_dev",
    ):
        if token in body:
            failures.append("FORBIDDEN_STAGE6_FEATURE:" + token)

    return {
        "candidate": "0059",
        "stage": "pointer-backed-render-tracking",
        "target_ref": TARGET_REF,
        "donor_reference": DONOR_REF,
        "result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "claims": {
            "render_tracking_source_active": True,
            "migt_device_node_created": False,
            "boost_policy_active": False,
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

    print("CANDIDATE0059_STAGE6=" + report["result"])
    print("RENDER_TRACKING_SOURCE_ACTIVE=true")
    print("MIGT_DEVICE_NODE_CREATED=false")
    print("BOOST_POLICY_ACTIVE=false")
    print("RUNTIME_TESTED=false")
    for item in report["failures"]:
        print("FAILURE=" + item)
    return 0 if report["result"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
