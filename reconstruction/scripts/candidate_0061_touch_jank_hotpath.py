#!/usr/bin/env python3
"""Candidate0061 Phase7 package-runtime/WALT hot-path correction.

TOUCH_PERF_ONLY overlay applied only after the Direct-302 5.4.302 tree has
materialized. Frozen Candidate0059 remains unchanged as the behavior reference.

Goals:
- preserve task-level history accounting required by MIGT;
- stop writing shared user history slots on every WALT accounting update;
- roll user history from system_long_wq, donor-style;
- restore a bounded pause/enable hook without adding a new userspace ABI;
- avoid global locks in the WALT hot path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    body = path.read_text()
    count = body.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement, found {count}: {old!r}")
    path.write_text(body.replace(old, new, 1))


def insert_after_once(path: Path, anchor: str, addition: str) -> None:
    replace_once(path, anchor, anchor + addition)


def apply(kernel: Path) -> None:
    hdr = kernel / "include/linux/pkg_stat.h"
    state = kernel / "kernel/sched/pkg_state.c"
    core = kernel / "kernel/sched/pkg_core.c"
    for p in (hdr, state, core):
        if not p.is_file():
            raise RuntimeError("missing Candidate0059 package-runtime source: " + str(p))

    # External package state is not part of frozen task/user KMI, so adding a
    # registry node here does not consume another Android KABI reserve.
    insert_after_once(
        hdr,
        "\tstruct list_head list;\n",
        "\tstruct list_head history_node;\n",
    )
    insert_after_once(
        hdr,
        "void pkg_user_state_release(struct user_struct *user);\n",
        "void pkg_roll_user_history(unsigned int slot);\n",
    )
    insert_after_once(
        hdr,
        "static inline void pkg_user_state_release(struct user_struct *user) { }\n",
        "static inline void pkg_roll_user_history(unsigned int slot) { }\n",
    )

    insert_after_once(
        state,
        "static struct package_runtime_info root_user_pkg_state;\n",
        "static LIST_HEAD(pkg_user_history_states);\n"
        "static DEFINE_SPINLOCK(pkg_user_history_lock);\n",
    )
    insert_after_once(
        state,
        "\tINIT_LIST_HEAD(&state->list);\n",
        "\tINIT_LIST_HEAD(&state->history_node);\n",
    )
    insert_after_once(
        state,
        "struct package_runtime_info *pkg_user_state(const struct user_struct *user)\n"
        "{\n\treturn READ_ONCE(user->pkg_rt);\n}\n",
        r'''
void pkg_roll_user_history(unsigned int slot)
{
	struct package_runtime_info *state;
	unsigned long flags;
	int i;

	if (slot >= HISTORY_ITMES)
		return;

	spin_lock_irqsave(&pkg_user_history_lock, flags);
	list_for_each_entry(state, &pkg_user_history_states, history_node) {
		state->sup_cluster_runtime[slot] =
			READ_ONCE(state->sup_cluster_runtime[HISTORY_ITMES]);
		state->big_cluster_runtime[slot] =
			READ_ONCE(state->big_cluster_runtime[HISTORY_ITMES]);
		state->little_cluster_runtime[slot] =
			READ_ONCE(state->little_cluster_runtime[HISTORY_ITMES]);
		for (i = 0; i < MAX_CLUSTER; i++) {
			state->front_runtime[slot][i] =
				READ_ONCE(state->front_runtime[HISTORY_ITMES][i]);
			state->back_runtime[slot][i] =
				READ_ONCE(state->back_runtime[HISTORY_ITMES][i]);
		}
	}
	spin_unlock_irqrestore(&pkg_user_history_lock, flags);
}
''',
    )

    replace_once(
        state,
        "\tpkg_state_init(state);\n\tWRITE_ONCE(user->pkg_rt, state);\n",
        "\tpkg_state_init(state);\n"
        "\tspin_lock(&pkg_user_history_lock);\n"
        "\tlist_add_tail(&state->history_node, &pkg_user_history_states);\n"
        "\tspin_unlock(&pkg_user_history_lock);\n"
        "\tWRITE_ONCE(user->pkg_rt, state);\n",
    )
    replace_once(
        state,
        "\tWRITE_ONCE(user->pkg_rt, NULL);\n\tkfree(state);\n",
        "\tspin_lock(&pkg_user_history_lock);\n"
        "\tif (!list_empty(&state->history_node))\n"
        "\t\tlist_del_init(&state->history_node);\n"
        "\tspin_unlock(&pkg_user_history_lock);\n"
        "\tWRITE_ONCE(user->pkg_rt, NULL);\n"
        "\tkfree(state);\n",
    )

    insert_after_once(core, "#include <linux/topology.h>\n", "#include <linux/workqueue.h>\n")
    replace_once(
        core,
        "static unsigned int pkg_history_slot;\n"
        "static u64 pkg_last_roll_jiffies;\n",
        "static unsigned int pkg_history_slot;\n"
        "static u64 pkg_last_roll_jiffies;\n"
        "static bool pkg_runtime_paused;\n"
        "static struct work_struct pkg_runtime_roll;\n",
    )
    insert_after_once(
        core,
        "void __weak migt_hook(struct task_struct *task, u64 delta, int cpu)\n"
        "{\n}\n",
        r'''
int __weak package_runtime_should_stop(void)
{
	return 0;
}

static void pkg_runtime_roll_wk(struct work_struct *work)
{
	unsigned int slot = READ_ONCE(pkg_history_slot) % HISTORY_ITMES;

	pkg_roll_user_history(slot);
	WRITE_ONCE(pkg_last_roll_jiffies, get_jiffies_64());
	WRITE_ONCE(pkg_history_slot, (slot + 1) % HISTORY_ITMES);
}
''',
    )

    # Candidate0059 wrote these shared user-history slots on every WALT update.
    # Donor semantics keep only aggregate user totals hot and snapshot user
    # history from deferred work.
    for old in (
        "\t\tuser_state->front_runtime[slot][cluster] =\n"
        "\t\t\tuser_state->front_runtime[HISTORY_ITMES][cluster];\n",
        "\t\tuser_state->back_runtime[slot][cluster] =\n"
        "\t\t\tuser_state->back_runtime[HISTORY_ITMES][cluster];\n",
        "\tuser_state->sup_cluster_runtime[slot] =\n"
        "\t\tuser_state->sup_cluster_runtime[HISTORY_ITMES];\n",
        "\tuser_state->big_cluster_runtime[slot] =\n"
        "\t\tuser_state->big_cluster_runtime[HISTORY_ITMES];\n",
        "\tuser_state->little_cluster_runtime[slot] =\n"
        "\t\tuser_state->little_cluster_runtime[HISTORY_ITMES];\n",
    ):
        replace_once(core, old, "")

    replace_once(
        core,
        "bool pkg_enable(void)\n"
        "{\n\treturn READ_ONCE(pkg_runtime_enabled);\n}\n",
        "bool pkg_enable(void)\n"
        "{\n"
        "\treturn READ_ONCE(pkg_runtime_enabled) &&\n"
        "\t       !READ_ONCE(pkg_runtime_paused);\n"
        "}\n",
    )
    replace_once(
        core,
        "void package_runtime_monitor(u64 now)\n"
        "{\n"
        "\tu64 window;\n\n"
        "\tif (!pkg_enable())\n"
        "\t\treturn;\n\n"
        "\twindow = (u64)READ_ONCE(pkg_runtime_window_secs) * HZ;\n"
        "\tif (now - READ_ONCE(pkg_last_roll_jiffies) < window)\n"
        "\t\treturn;\n\n"
        "\tWRITE_ONCE(pkg_last_roll_jiffies, now);\n"
        "\tWRITE_ONCE(pkg_history_slot,\n"
        "\t\t   (READ_ONCE(pkg_history_slot) + 1) % HISTORY_ITMES);\n"
        "}\n",
        "void package_runtime_monitor(u64 now)\n"
        "{\n"
        "\tu64 window;\n\n"
        "\tWRITE_ONCE(pkg_runtime_paused, !!package_runtime_should_stop());\n"
        "\tif (!pkg_enable())\n"
        "\t\treturn;\n\n"
        "\twindow = (u64)READ_ONCE(pkg_runtime_window_secs) * HZ;\n"
        "\tif (now - READ_ONCE(pkg_last_roll_jiffies) < window)\n"
        "\t\treturn;\n\n"
        "\tqueue_work_on(0, system_long_wq, &pkg_runtime_roll);\n"
        "}\n",
    )
    replace_once(
        core,
        "\tWRITE_ONCE(pkg_history_slot, 0);\n"
        "\tWRITE_ONCE(pkg_last_roll_jiffies, get_jiffies_64());\n"
        "\tWRITE_ONCE(pkg_runtime_enabled, true);\n",
        "\tWRITE_ONCE(pkg_history_slot, 0);\n"
        "\tWRITE_ONCE(pkg_last_roll_jiffies, get_jiffies_64());\n"
        "\tWRITE_ONCE(pkg_runtime_paused, false);\n"
        "\tINIT_WORK(&pkg_runtime_roll, pkg_runtime_roll_wk);\n"
        "\tWRITE_ONCE(pkg_runtime_enabled, true);\n",
    )


def verify(kernel: Path) -> dict:
    hdr = (kernel / "include/linux/pkg_stat.h").read_text()
    state = (kernel / "kernel/sched/pkg_state.c").read_text()
    core = (kernel / "kernel/sched/pkg_core.c").read_text()
    failures = []

    required = {
        "header_history_node": "struct list_head history_node;" in hdr,
        "header_roll_helper": "void pkg_roll_user_history(unsigned int slot);" in hdr,
        "state_registry": "pkg_user_history_states" in state,
        "state_roll_helper": "void pkg_roll_user_history(unsigned int slot)" in state,
        "deferred_work": "queue_work_on(0, system_long_wq, &pkg_runtime_roll);" in core,
        "work_init": "INIT_WORK(&pkg_runtime_roll, pkg_runtime_roll_wk);" in core,
        "pause_hook": "package_runtime_should_stop" in core and "pkg_runtime_paused" in core,
        "migt_retained": "migt_hook(task, delta, cpu);" in core,
        "task_history_retained": "task_state->sup_cluster_runtime[slot]" in core,
    }
    for name, ok in required.items():
        if not ok:
            failures.append("MISSING:" + name)

    forbidden_hot_writes = (
        "user_state->front_runtime[slot][cluster] =",
        "user_state->back_runtime[slot][cluster] =",
        "user_state->sup_cluster_runtime[slot] =",
        "user_state->big_cluster_runtime[slot] =",
        "user_state->little_cluster_runtime[slot] =",
    )
    for token in forbidden_hot_writes:
        if token in core:
            failures.append("HOT_USER_HISTORY_WRITE_REMAINS:" + token)

    return {
        "candidate": "0061",
        "classification": "TOUCH_PERF_ONLY",
        "phase": "7A_package_runtime_walt",
        "result": "PASS" if not failures else "FAIL",
        "frozen_candidate0059_modified": False,
        "donor_semantics": {
            "pause_hook": True,
            "user_history_roll_system_long_wq": True,
            "task_history_hotpath_retained": True,
            "user_history_hotpath_copies_removed": True,
        },
        "failures": failures,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("apply", "verify"))
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    kernel = args.source.resolve()
    if args.mode == "apply":
        apply(kernel)
    report = verify(kernel)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("C0061_TOUCH_JANK_HOTPATH=" + report["result"])
    print("CLASSIFICATION=TOUCH_PERF_ONLY")
    for item in report["failures"]:
        print("FAILURE=" + item)
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
