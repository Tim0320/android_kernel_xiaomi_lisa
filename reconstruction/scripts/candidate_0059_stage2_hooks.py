#!/usr/bin/env python3
"""Candidate0059 Stage2 package-runtime membership + semantic hook bridge.

Requires Stage1 to be applied first. Stage2 wires exact stock-lineage lifecycle,
split-WALT and do_timer landing points, but deliberately keeps pkg_enable()
weak-false and update_pkg_load() weak-noop until the actual pkg_core/MIGT
implementation is ported in a later stage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TARGET_REF = "6e568aabc77a06fa787baec1d9e60e4b559874a3"
DONOR_A = "projects-nexus/nexus_kernel_xiaomi_sm8250@d26c193dcd97812a9a565ac40fe5092cc9a18fbf"
DONOR_B = "Danda420/kernel_xiaomi_sm8250@01cbd2157daa54b46154be5c5c7ef5ff6a283a15"

PKG_BRIDGE_C = r'''// SPDX-License-Identifier: GPL-2.0-only
/*
 * Candidate0059 Stage2 bridge.
 *
 * These weak defaults make the exact WALT/timekeeping hooks linkable before
 * pkg_core/MIGT are introduced. pkg_enable() is deliberately false, so Stage2
 * does not pretend to restore runtime accounting or performance behavior.
 */
#include <linux/compiler.h>
#include <linux/pkg_stat.h>
#include <linux/sched.h>

bool __weak pkg_enable(void)
{
	return false;
}

void __weak update_pkg_load(struct task_struct *task, int cpu, int flag,
			    u64 wallclock, u64 delta)
{
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

def insert_before(path: Path, anchor: str, addition: str) -> None:
    replace_once(path, anchor, addition + anchor)

def apply(root: Path) -> None:
    # Hard dependency on Stage1.
    if not (root / "kernel/sched/pkg_state.c").is_file():
        raise RuntimeError("Stage1 pkg_state.c missing")
    if "ANDROID_KABI_USE(8, struct package_runtime_info *pkg_rt);" not in (root / "include/linux/sched.h").read_text():
        raise RuntimeError("Stage1 task KABI pointer missing")

    bridge = root / "kernel/sched/pkg_bridge.c"
    if bridge.exists():
        raise RuntimeError("Stage2 bridge already exists")
    bridge.write_text(PKG_BRIDGE_C)

    pkg_h = root / "include/linux/pkg_stat.h"
    insert_after(
        pkg_h,
        "#define MINOR_TASK (1U << MIGT_MINOR_TASK)\n",
        "#define PKG_TASK_BUSY 1\n",
    )
    replace_once(
        pkg_h,
        "\trwlock_t lock;\n\tstruct list_head list;\n",
        "\trwlock_t lock;\n\tstruct list_head list;\n"
        "\tstruct task_struct *owner_task;\n"
        "\tstruct user_struct *owner_user;\n",
    )
    insert_after(
        pkg_h,
        "void pkg_user_state_release(struct user_struct *user);\n",
        "void pkg_task_bind_user(struct task_struct *task, struct user_struct *user);\n"
        "void pkg_task_unbind_user(struct task_struct *task);\n"
        "void pkg_task_rebind_user(struct task_struct *task, struct user_struct *user);\n"
        "bool pkg_enable(void);\n"
        "void update_pkg_load(struct task_struct *task, int cpu, int flag,\n"
        "\t\t     u64 wallclock, u64 delta);\n"
        "void package_runtime_monitor(u64 now);\n",
    )
    insert_after(
        pkg_h,
        "static inline void pkg_user_state_release(struct user_struct *user) { }\n",
        "static inline void pkg_task_bind_user(struct task_struct *task, struct user_struct *user) { }\n"
        "static inline void pkg_task_unbind_user(struct task_struct *task) { }\n"
        "static inline void pkg_task_rebind_user(struct task_struct *task, struct user_struct *user) { }\n"
        "static inline bool pkg_enable(void) { return false; }\n"
        "static inline void update_pkg_load(struct task_struct *task, int cpu, int flag,\n"
        "\t\t\t\t   u64 wallclock, u64 delta) { }\n"
        "static inline void package_runtime_monitor(u64 now) { }\n",
    )

    state_c = root / "kernel/sched/pkg_state.c"
    insert_after(
        state_c,
        "struct package_runtime_info *pkg_user_state(const struct user_struct *user)\n"
        "{\n\treturn READ_ONCE(user->pkg_rt);\n}\n",
        r'''
void pkg_task_unbind_user(struct task_struct *task)
{
	struct package_runtime_info *task_state = pkg_task_state(task);
	struct package_runtime_info *user_state;
	struct user_struct *user;
	unsigned long flags;

	if (!task_state)
		return;

	user = READ_ONCE(task_state->owner_user);
	if (!user)
		return;

	user_state = pkg_user_state(user);
	if (!user_state) {
		WRITE_ONCE(task_state->owner_user, NULL);
		INIT_LIST_HEAD(&task_state->list);
		return;
	}

	write_lock_irqsave(&user_state->lock, flags);
	if (!list_empty(&task_state->list))
		list_del_init(&task_state->list);
	WRITE_ONCE(task_state->owner_user, NULL);
	write_unlock_irqrestore(&user_state->lock, flags);
}

void pkg_task_bind_user(struct task_struct *task, struct user_struct *user)
{
	struct package_runtime_info *task_state = pkg_task_state(task);
	struct package_runtime_info *user_state;
	unsigned long flags;

	if (!task_state || !user)
		return;

	user_state = pkg_user_state(user);
	if (!user_state)
		return;

	if (READ_ONCE(task_state->owner_user) == user &&
	    !list_empty(&task_state->list))
		return;

	if (READ_ONCE(task_state->owner_user))
		pkg_task_unbind_user(task);

	write_lock_irqsave(&user_state->lock, flags);
	if (WARN_ON_ONCE(!list_empty(&task_state->list))) {
		write_unlock_irqrestore(&user_state->lock, flags);
		return;
	}
	list_add_tail(&task_state->list, &user_state->list);
	WRITE_ONCE(task_state->owner_user, user);
	write_unlock_irqrestore(&user_state->lock, flags);
}

void pkg_task_rebind_user(struct task_struct *task, struct user_struct *user)
{
	struct package_runtime_info *task_state = pkg_task_state(task);

	if (!task_state || READ_ONCE(task_state->owner_user) == user)
		return;

	pkg_task_unbind_user(task);
	pkg_task_bind_user(task, user);
}
''',
    )
    insert_after(
        state_c,
        "\tpkg_state_init(state);\n\tWRITE_ONCE(task->pkg_rt, state);\n",
        "\tstate->owner_task = task;\n",
    )
    # The previous insertion lands after WRITE_ONCE; owner assignment remains
    # safe because the child task is not published yet.
    insert_after(
        state_c,
        "\tpkg_state_init(state);\n\tWRITE_ONCE(user->pkg_rt, state);\n",
        "\tstate->owner_user = user;\n",
    )

    makefile = root / "kernel/sched/Makefile"
    insert_after(
        makefile,
        "obj-$(CONFIG_PACKAGE_RUNTIME_INFO) += pkg_state.o\n",
        "obj-$(CONFIG_PACKAGE_RUNTIME_INFO) += pkg_bridge.o\n",
    )

    fork_c = root / "kernel/fork.c"
    insert_after(
        fork_c,
        "\tretval = copy_creds(p, clone_flags);\n"
        "\tif (retval < 0)\n"
        "\t\tgoto bad_fork_free;\n",
        "\tpkg_task_bind_user(p, p->cred->user);\n",
    )
    insert_before(
        fork_c,
        "bad_fork_cleanup_count:\n",
        "\tpkg_task_unbind_user(p);\n",
    )

    exit_c = root / "kernel/exit.c"
    insert_after(exit_c, "#include <linux/sched/task.h>\n", "#include <linux/pkg_stat.h>\n")
    insert_after(exit_c, "\tint zap_leader;\nrepeat:\n", "\tpkg_task_unbind_user(p);\n")

    cred_c = root / "kernel/cred.c"
    insert_after(cred_c, "#include <linux/sched.h>\n", "#include <linux/pkg_stat.h>\n")
    replace_once(
        cred_c,
        "\trcu_assign_pointer(task->real_cred, new);\n"
        "\trcu_assign_pointer(task->cred, new);\n"
        "\tif (new->user != old->user)\n"
        "\t\tatomic_dec(&old->user->processes);",
        "\trcu_assign_pointer(task->real_cred, new);\n"
        "\trcu_assign_pointer(task->cred, new);\n"
        "\tif (new->user != old->user) {\n"
        "\t\tpkg_task_rebind_user(task, new->user);\n"
        "\t\tatomic_dec(&old->user->processes);\n"
        "\t}",
    )

    walt = root / "kernel/sched/walt/walt.c"
    insert_after(walt, "#include <linux/sched/stat.h>\n", "#include <linux/pkg_stat.h>\n")
    insert_before(
        walt,
        "unsigned int sysctl_sched_task_unfilter_period = 100000000;\n",
        r'''#if IS_ENABLED(CONFIG_PACKAGE_RUNTIME_INFO)
static int account_pkg_busy_time(struct rq *rq, struct task_struct *p, int event)
{
	if (is_idle_task(p)) {
		if (event == PICK_NEXT_TASK)
			return 0;
		return 1;
	}

	if (exiting_task(p))
		return 0;

	if (event == TASK_WAKE ||
	    event == PICK_NEXT_TASK ||
	    event == TASK_MIGRATE)
		return 0;

	if (event == TASK_UPDATE) {
		if (rq->curr == p)
			return 1;
		return 0;
	}

	return 1;
}
#endif

''',
    )
    insert_after(
        walt,
        "\tupdate_task_pred_demand(rq, p, event);\n",
        r'''#if IS_ENABLED(CONFIG_PACKAGE_RUNTIME_INFO)
	if (pkg_enable() && account_pkg_busy_time(rq, p, event)) {
		int fstat = PKG_TASK_BUSY;
		u64 delta;

		if (is_idle_task(p))
			delta = irqtime;
		else
			delta = wallclock - p->wts.mark_start;
		delta = scale_exec_time(delta, rq);
		update_pkg_load(p, cpu_of(rq), fstat, wallclock, delta);
	}
#endif
''',
    )

    tk = root / "kernel/time/timekeeping.c"
    insert_after(tk, "#include <linux/random.h>\n", "#include <linux/pkg_stat.h>\n")
    insert_before(
        tk,
        "/*\n * Must hold jiffies_lock\n */\nvoid do_timer(unsigned long ticks)\n",
        r'''#if IS_ENABLED(CONFIG_PACKAGE_RUNTIME_INFO)
void __weak package_runtime_monitor(u64 now) { }
#endif

''',
    )
    insert_after(
        tk,
        "\tjiffies_64 += ticks;\n",
        "#if IS_ENABLED(CONFIG_PACKAGE_RUNTIME_INFO)\n"
        "\tpackage_runtime_monitor(jiffies_64);\n"
        "#endif\n",
    )

def verify(root: Path) -> dict:
    failures: list[str] = []
    checks = {
        "include/linux/pkg_stat.h": (
            "owner_task",
            "owner_user",
            "PKG_TASK_BUSY",
            "pkg_task_rebind_user",
            "update_pkg_load",
        ),
        "kernel/sched/pkg_state.c": (
            "pkg_task_bind_user",
            "pkg_task_unbind_user",
            "pkg_task_rebind_user",
        ),
        "kernel/sched/pkg_bridge.c": (
            "bool __weak pkg_enable",
            "void __weak update_pkg_load",
        ),
        "kernel/fork.c": (
            "pkg_task_bind_user(p, p->cred->user);",
            "pkg_task_unbind_user(p);",
        ),
        "kernel/exit.c": ("pkg_task_unbind_user(p);",),
        "kernel/cred.c": ("pkg_task_rebind_user(task, new->user);",),
        "kernel/sched/walt/walt.c": (
            "static int account_pkg_busy_time",
            "update_pkg_load(p, cpu_of(rq), fstat, wallclock, delta);",
        ),
        "kernel/time/timekeeping.c": (
            "void __weak package_runtime_monitor",
            "package_runtime_monitor(jiffies_64);",
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

    joined = "\n".join((root / p).read_text() for p in (
        "kernel/sched/pkg_bridge.c",
        "kernel/sched/pkg_state.c",
        "kernel/sched/walt/walt.c",
    ))
    for forbidden in ("/dev/metis", 'name = "metis"', "iorap_dev", "migt_ioctl"):
        if forbidden in joined:
            failures.append("FORBIDDEN_STAGE2_FEATURE:" + forbidden)

    return {
        "candidate": "0059",
        "stage": "membership-semantic-hook-bridge",
        "target_ref": TARGET_REF,
        "donor_evidence": [DONOR_A, DONOR_B],
        "result": "PASS" if not failures else "FAIL",
        "files": evidence,
        "failures": failures,
        "claims": {
            "pkg_enable_runtime": False,
            "runtime_accounting_active": False,
            "full_migt_ported": False,
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

    print("CANDIDATE0059_STAGE2=" + report["result"])
    print("PKG_ENABLE_RUNTIME=false")
    print("RUNTIME_ACCOUNTING_ACTIVE=false")
    print("FULL_MIGT_PORTED=false")
    print("RUNTIME_TESTED=false")
    for item in report["failures"]:
        print("FAILURE=" + item)
    return 0 if report["result"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
