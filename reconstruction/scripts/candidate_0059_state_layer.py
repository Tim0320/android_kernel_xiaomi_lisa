#!/usr/bin/env python3
"""Candidate0059 Stage1 pointer-backed package-runtime state layer.

This bounded mutator applies only the ABI-safe external-state plumbing needed
before MIGT/package-runtime accounting is ported. It deliberately does NOT add
MIGT ioctls, WALT accounting hooks, cpuset boosts, Metis aliases, or iorap
shims.

Usage:
  candidate_0059_state_layer.py apply --source <kernel>
  candidate_0059_state_layer.py verify --source <kernel>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TARGET_REF = "6e568aabc77a06fa787baec1d9e60e4b559874a3"

PKG_STAT_H = r'''/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _LINUX_PKG_STAT_H
#define _LINUX_PKG_STAT_H

#include <linux/cpumask.h>
#include <linux/list.h>
#include <linux/spinlock_types.h>
#include <linux/types.h>

#define HISTORY_ITMES 4
#define HISTORY_WINDOWS (HISTORY_ITMES + 2)
#define NUM_MIGT_BUCKETS 10
#define USER_PKG_MIN_UID 10000

struct task_struct;
struct user_struct;

enum cluster_type {
	LITTLE_CLUSTER = 0,
	MID_CLUSTER,
	BIG_CLUSTER,
	CLUSTER_TYPES,
};

#define MAX_CLUSTER CLUSTER_TYPES

enum PKG_STATUS_TYPE {
	NO_STATUS,
	FRONT,
	BACK,
	PKG_STATUS_NUM,
};

enum MIGT_TASK_TYPE {
	MIGT_NORMAL_TASK,
	GAME_NORMAL_TASK,
	GAME_IP_TASK,
	GAME_VIP_TASK,
	GAME_QRENDER_TASK,
	GAME_DQRENDER_TASK,
	GAME_SUPER_TASK,
	MIGT_MINOR_TASK,
	MI_VIP_TASK,
	GAME_TASK_LEVELS
};

#define MINOR_TASK (1U << MIGT_MINOR_TASK)

#ifdef CONFIG_PACKAGE_RUNTIME_INFO
struct package_runtime_info {
	rwlock_t lock;
	struct list_head list;
	u64 sup_cluster_runtime[HISTORY_WINDOWS];
	u64 big_cluster_runtime[HISTORY_WINDOWS];
	u64 little_cluster_runtime[HISTORY_WINDOWS];
	enum PKG_STATUS_TYPE edt;
	u64 front_runtime[HISTORY_WINDOWS][MAX_CLUSTER];
	u64 back_runtime[HISTORY_WINDOWS][MAX_CLUSTER];
#ifdef CONFIG_MILLET
	int millet_freeze_flag;
#endif
	struct {
		cpumask_t cpus_allowed;
		u32 migt_count;
		enum MIGT_TASK_TYPE flag;
		u32 wake_render;
		unsigned long boost_end;
		u64 run_times;
		u64 prev_sum;
		u32 max_exec;
		u64 fps_exec;
		u64 fps_mexec;
#ifdef VTASK_BOOST_DEBUG
		u32 boostat[NUM_MIGT_BUCKETS];
#endif
		u32 bucket[NUM_MIGT_BUCKETS];
	} migt;
};

static inline bool user_pkg(int uid)
{
	return uid > USER_PKG_MIN_UID;
}

struct package_runtime_info *pkg_task_state(const struct task_struct *task);
struct package_runtime_info *pkg_user_state(const struct user_struct *user);
int pkg_task_state_prepare(struct task_struct *task);
void pkg_task_state_release(struct task_struct *task);
int pkg_user_state_prepare(struct user_struct *user);
void pkg_user_state_release(struct user_struct *user);
#else
static inline bool user_pkg(int uid) { return false; }
static inline struct package_runtime_info *pkg_task_state(const struct task_struct *task)
{
	return NULL;
}
static inline struct package_runtime_info *pkg_user_state(const struct user_struct *user)
{
	return NULL;
}
static inline int pkg_task_state_prepare(struct task_struct *task) { return 0; }
static inline void pkg_task_state_release(struct task_struct *task) { }
static inline int pkg_user_state_prepare(struct user_struct *user) { return 0; }
static inline void pkg_user_state_release(struct user_struct *user) { }
#endif

#endif /* _LINUX_PKG_STAT_H */
'''

PKG_STATE_C = r'''// SPDX-License-Identifier: GPL-2.0-only
/*
 * Candidate0059 ABI-safe backing storage for Xiaomi package-runtime state.
 */
#include <linux/compiler.h>
#include <linux/pkg_stat.h>
#include <linux/sched.h>
#include <linux/sched/user.h>
#include <linux/slab.h>
#include <linux/spinlock.h>

static struct package_runtime_info root_user_pkg_state;

static void pkg_state_init(struct package_runtime_info *state)
{
	rwlock_init(&state->lock);
	INIT_LIST_HEAD(&state->list);
	state->edt = BACK;
	cpumask_copy(&state->migt.cpus_allowed, cpu_possible_mask);
	state->migt.flag = MIGT_NORMAL_TASK;
}

struct package_runtime_info *pkg_task_state(const struct task_struct *task)
{
	return READ_ONCE(task->pkg_rt);
}

struct package_runtime_info *pkg_user_state(const struct user_struct *user)
{
	return READ_ONCE(user->pkg_rt);
}

int pkg_task_state_prepare(struct task_struct *task)
{
	struct package_runtime_info *state;

	/*
	 * dup_task_struct() copied the parent's KABI slot. Clear that borrowed
	 * pointer before any failure path can reach free_task().
	 */
	WRITE_ONCE(task->pkg_rt, NULL);
	state = kzalloc(sizeof(*state), GFP_KERNEL);
	if (!state)
		return -ENOMEM;

	pkg_state_init(state);
	WRITE_ONCE(task->pkg_rt, state);
	return 0;
}

void pkg_task_state_release(struct task_struct *task)
{
	struct package_runtime_info *state = pkg_task_state(task);

	if (!state)
		return;

	/*
	 * Stage1 never links task state into a user list. Later stages must
	 * unlink under the owning user lock before this release point.
	 */
	if (WARN_ON_ONCE(!list_empty(&state->list)))
		return;

	WRITE_ONCE(task->pkg_rt, NULL);
	kfree(state);
}

int pkg_user_state_prepare(struct user_struct *user)
{
	struct package_runtime_info *state;

	if (user == &root_user) {
		state = &root_user_pkg_state;
		memset(state, 0, sizeof(*state));
	} else {
		state = kzalloc(sizeof(*state), GFP_KERNEL);
		if (!state)
			return -ENOMEM;
	}

	pkg_state_init(state);
	WRITE_ONCE(user->pkg_rt, state);
	return 0;
}

void pkg_user_state_release(struct user_struct *user)
{
	struct package_runtime_info *state = pkg_user_state(user);

	if (!state || user == &root_user)
		return;

	if (WARN_ON_ONCE(!list_empty(&state->list)))
		return;

	WRITE_ONCE(user->pkg_rt, NULL);
	kfree(state);
}
'''

KCONFIG_BLOCK = '''config PACKAGE_RUNTIME_INFO
\tbool "Xiaomi package runtime accounting state"
\tdepends on MIHW
\tdefault n
\thelp
\t  Provide the ABI-safe backing state required by the stock Lisa
\t  package-runtime/MIGT scheduler chain. Candidate0059 Stage1 only
\t  provides state lifetime plumbing; it does not enable MIGT boosts.

'''

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def replace_once(path: Path, old: str, new: str) -> None:
    body = path.read_text()
    count = body.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement, found {count}: {old!r}")
    path.write_text(body.replace(old, new, 1))

def insert_after_once(path: Path, anchor: str, addition: str) -> None:
    replace_once(path, anchor, anchor + addition)

def apply(root: Path) -> None:
    if not (root / "include/linux/android_kabi.h").is_file():
        raise RuntimeError("not a Lisa kernel source tree")

    pkg_h = root / "include/linux/pkg_stat.h"
    pkg_c = root / "kernel/sched/pkg_state.c"
    if pkg_h.exists() or pkg_c.exists():
        raise RuntimeError("Stage1 target files already exist; refuse double apply")
    pkg_h.write_text(PKG_STAT_H)
    pkg_c.write_text(PKG_STATE_C)

    kconfig = root / "drivers/mihw/Kconfig"
    if "config PACKAGE_RUNTIME_INFO" in kconfig.read_text():
        raise RuntimeError("PACKAGE_RUNTIME_INFO already declared")
    kconfig.write_text(KCONFIG_BLOCK + kconfig.read_text())

    makefile = root / "kernel/sched/Makefile"
    insert_after_once(
        makefile,
        "obj-$(CONFIG_SCHED_WALT) += walt/\n",
        "obj-$(CONFIG_PACKAGE_RUNTIME_INFO) += pkg_state.o\n",
    )

    sched_h = root / "include/linux/sched.h"
    insert_after_once(sched_h, "struct task_group;\n", "struct package_runtime_info;\n")
    replace_once(
        sched_h,
        "\tANDROID_KABI_RESERVE(7);\n\tANDROID_KABI_RESERVE(8);",
        "\tANDROID_KABI_RESERVE(7);\n"
        "#ifdef CONFIG_PACKAGE_RUNTIME_INFO\n"
        "\tANDROID_KABI_USE(8, struct package_runtime_info *pkg_rt);\n"
        "#else\n"
        "\tANDROID_KABI_RESERVE(8);\n"
        "#endif",
    )

    user_h = root / "include/linux/sched/user.h"
    insert_after_once(
        user_h,
        "#include <linux/android_kabi.h>\n",
        "\nstruct package_runtime_info;\n",
    )
    replace_once(
        user_h,
        "\tANDROID_KABI_RESERVE(1);\n\tANDROID_KABI_RESERVE(2);",
        "\tANDROID_KABI_RESERVE(1);\n"
        "#ifdef CONFIG_PACKAGE_RUNTIME_INFO\n"
        "\tANDROID_KABI_USE(2, struct package_runtime_info *pkg_rt);\n"
        "#else\n"
        "\tANDROID_KABI_RESERVE(2);\n"
        "#endif",
    )

    fork_c = root / "kernel/fork.c"
    insert_after_once(
        fork_c,
        "#include <linux/sched/user.h>\n",
        "#include <linux/pkg_stat.h>\n",
    )
    insert_after_once(
        fork_c,
        "\trt_mutex_init_task(p);\n",
        "\n\tretval = pkg_task_state_prepare(p);\n"
        "\tif (retval)\n"
        "\t\tgoto bad_fork_free;\n",
    )
    insert_after_once(
        fork_c,
        "\tif (tsk->flags & PF_KTHREAD)\n\t\tfree_kthread_struct(tsk);\n",
        "\tpkg_task_state_release(tsk);\n",
    )

    user_c = root / "kernel/user.c"
    insert_after_once(
        user_c,
        "#include <linux/sched/user.h>\n",
        "#include <linux/pkg_stat.h>\n",
    )
    insert_after_once(
        user_c,
        "\tuid_hash_remove(up);\n\tspin_unlock_irqrestore(&uidhash_lock, flags);\n",
        "\tpkg_user_state_release(up);\n",
    )
    insert_after_once(
        user_c,
        "\t\tratelimit_set_flags(&new->ratelimit, RATELIMIT_MSG_ON_RELEASE);\n",
        "\n\t\tif (pkg_user_state_prepare(new)) {\n"
        "\t\t\tkmem_cache_free(uid_cachep, new);\n"
        "\t\t\treturn NULL;\n"
        "\t\t}\n",
    )
    replace_once(
        user_c,
        "\t\tif (up) {\n\t\t\tkmem_cache_free(uid_cachep, new);",
        "\t\tif (up) {\n"
        "\t\t\tpkg_user_state_release(new);\n"
        "\t\t\tkmem_cache_free(uid_cachep, new);",
    )
    insert_after_once(
        user_c,
        "\tfor(n = 0; n < UIDHASH_SZ; ++n)\n\t\tINIT_HLIST_HEAD(uidhash_table + n);\n",
        "\n\tif (pkg_user_state_prepare(&root_user))\n"
        "\t\treturn -ENOMEM;\n",
    )

def verify(root: Path) -> dict:
    failures: list[str] = []
    required = {
        "include/linux/pkg_stat.h": [
            "struct package_runtime_info {",
            "pkg_task_state_prepare",
            "pkg_user_state_prepare",
        ],
        "kernel/sched/pkg_state.c": [
            "WRITE_ONCE(task->pkg_rt, NULL);",
            "root_user_pkg_state",
            "WARN_ON_ONCE(!list_empty(&state->list))",
        ],
        "include/linux/sched.h": [
            "ANDROID_KABI_USE(8, struct package_runtime_info *pkg_rt);",
        ],
        "include/linux/sched/user.h": [
            "ANDROID_KABI_USE(2, struct package_runtime_info *pkg_rt);",
        ],
        "kernel/fork.c": [
            "pkg_task_state_prepare(p);",
            "pkg_task_state_release(tsk);",
        ],
        "kernel/user.c": [
            "pkg_user_state_prepare(new)",
            "pkg_user_state_release(new);",
            "pkg_user_state_prepare(&root_user)",
        ],
        "kernel/sched/Makefile": [
            "obj-$(CONFIG_PACKAGE_RUNTIME_INFO) += pkg_state.o",
        ],
        "drivers/mihw/Kconfig": [
            "config PACKAGE_RUNTIME_INFO",
        ],
    }
    evidence = {}
    for rel, markers in required.items():
        p = root / rel
        body = p.read_text() if p.is_file() else ""
        evidence[rel] = {
            "exists": p.is_file(),
            "sha256": sha256(p) if p.is_file() else None,
        }
        if not p.is_file():
            failures.append("MISSING_FILE:" + rel)
            continue
        for marker in markers:
            if marker not in body:
                failures.append("MISSING_MARKER:" + rel + ":" + marker)

    joined = "\n".join((root / p).read_text() for p in (
        "include/linux/pkg_stat.h",
        "kernel/sched/pkg_state.c",
    ))
    for forbidden in ("/dev/metis", 'name = "metis"', "iorap_dev", "migt_ioctl"):
        if forbidden in joined:
            failures.append("FORBIDDEN_STAGE1_FEATURE:" + forbidden)

    return {
        "candidate": "0059",
        "stage": "package-runtime-state-layer",
        "target_ref": TARGET_REF,
        "result": "PASS" if not failures else "FAIL",
        "files": evidence,
        "failures": failures,
        "claims": {
            "full_migt_ported": False,
            "walt_hooks_ported": False,
            "kernel_compiled": False,
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
    print("CANDIDATE0059_STATE_LAYER=" + report["result"])
    print("TARGET_REF=" + TARGET_REF)
    print("SCOPE=pointer-backed-state-only")
    print("FULL_MIGT_PORTED=false")
    print("RUNTIME_TESTED=false")
    for item in report["failures"]:
        print("FAILURE=" + item)
    return 0 if report["result"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
