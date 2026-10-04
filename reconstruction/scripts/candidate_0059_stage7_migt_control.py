#!/usr/bin/env python3
"""Candidate0059 Stage7 bounded legacy MIGT device control.

Requires Stages1-6. Restores the stock-lineage miscdevice identity and the two
render-state ioctls whose semantics are already present. Frequency ceiling and
boost policy remain explicitly unsupported until their source is ported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TARGET_REF = "6e568aabc77a06fa787baec1d9e60e4b559874a3"
DONOR_REF = "LeviMarvin/android_kernel_xiaomi_alioth@e7065bc9ead4a0ca183f51101e07dd45a9d5c558"

MIGT_C = r'''// SPDX-License-Identifier: GPL-2.0-only
/*
 * Candidate0059 Stage7: bounded legacy MIGT control device.
 *
 * Legacy Xiaomi userspace identifies commands only through _IOC_NR(cmd):
 *   1 QUEUE_BUFFER, 2 DEQUEUE_BUFFER, 3 SET_CEILING.
 *
 * QUEUE/DEQUEUE are implemented because Stage6 provides real render tracking.
 * SET_CEILING is deliberately rejected until the corresponding frequency
 * ceiling policy is ported. Unknown commands return -ENOTTY, never fake success.
 */
#define pr_fmt(fmt) "migt: " fmt

#include <linux/cred.h>
#include <linux/errno.h>
#include <linux/fs.h>
#include <linux/init.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/pkg_stat.h>
#include <linux/sched.h>
#include <linux/user_namespace.h>

enum migt_cmd {
	QUEUE_BUFFER = 1,
	DEQUEUE_BUFFER,
	SET_CEILING,
};

static DEFINE_MUTEX(migt_control_lock);
static uid_t last_traced_uid;
static bool migt_device_ready;

int get_cur_render_uid(void)
{
	return READ_ONCE(last_traced_uid);
}

int migt_enable(void)
{
	return READ_ONCE(migt_device_ready);
}

int package_runtime_should_stop(void)
{
	/* Boost policy is intentionally not active in Stage7. */
	return 1;
}

static int migt_open(struct inode *inode, struct file *file)
{
	return 0;
}

static int migt_release(struct inode *inode, struct file *file)
{
	return 0;
}

static long migt_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	uid_t traced_uid = from_kuid(&init_user_ns, current_uid());
	unsigned int user_cmd = _IOC_NR(cmd);

	(void)file;
	(void)arg;

	switch (user_cmd) {
	case QUEUE_BUFFER:
		mutex_lock(&migt_control_lock);
		if (traced_uid != last_traced_uid) {
			reset_render_info(RENDER_QUEUE_THREAD);
			reset_render_info(RENDER_DEQUEUE_THREAD);
			game_load_reset();
			WRITE_ONCE(last_traced_uid, traced_uid);
		}
		update_render_info(current, RENDER_QUEUE_THREAD);
		mutex_unlock(&migt_control_lock);
		return 0;

	case DEQUEUE_BUFFER:
		update_render_info(current, RENDER_DEQUEUE_THREAD);
		return 0;

	case SET_CEILING:
		return -EOPNOTSUPP;

	default:
		return -ENOTTY;
	}
}

static const struct file_operations migt_fops = {
	.owner = THIS_MODULE,
	.open = migt_open,
	.release = migt_release,
	.unlocked_ioctl = migt_ioctl,
};

static struct miscdevice migt_misc = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = "migt",
	.fops = &migt_fops,
};

static int __init migt_init(void)
{
	int ret;

	ret = misc_register(&migt_misc);
	if (ret)
		return ret;

	WRITE_ONCE(last_traced_uid, 0);
	WRITE_ONCE(migt_device_ready, true);
	pr_info("Candidate0059 bounded legacy MIGT control registered\n");
	return 0;
}
late_initcall(migt_init);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Candidate0059 bounded legacy MIGT control");
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
    if not (root / "kernel/sched/migt_render.c").is_file():
        raise RuntimeError("Stage6 render tracking missing")
    if "update_render_info" not in (root / "kernel/sched/migt_render.c").read_text():
        raise RuntimeError("Stage6 render semantics missing")

    driver = root / "drivers/mihw/migt.c"
    if driver.exists():
        raise RuntimeError("Stage7 drivers/mihw/migt.c already exists")
    driver.write_text(MIGT_C)

    makefile = root / "drivers/mihw/Makefile"
    body = makefile.read_text()
    if "CONFIG_MIGT" in body:
        raise RuntimeError("CONFIG_MIGT driver object already wired")
    makefile.write_text(body + "\nobj-$(CONFIG_MIGT) += migt.o\n")

    pkg_h = root / "include/linux/pkg_stat.h"
    insert_after(
        pkg_h,
        "int game_load_init(void);\n",
        "int get_cur_render_uid(void);\n"
        "int migt_enable(void);\n"
        "int package_runtime_should_stop(void);\n",
    )
    insert_after(
        pkg_h,
        "static inline int game_load_init(void) { return 0; }\n",
        "static inline int get_cur_render_uid(void) { return -1; }\n"
        "static inline int migt_enable(void) { return 0; }\n"
        "static inline int package_runtime_should_stop(void) { return 1; }\n",
    )

def verify(root: Path) -> dict:
    failures: list[str] = []
    checks = {
        "drivers/mihw/migt.c": (
            "QUEUE_BUFFER = 1",
            "DEQUEUE_BUFFER",
            "SET_CEILING",
            'name = "migt"',
            "update_render_info(current, RENDER_QUEUE_THREAD);",
            "update_render_info(current, RENDER_DEQUEUE_THREAD);",
            "return -EOPNOTSUPP;",
            "return -ENOTTY;",
            "late_initcall(migt_init);",
            "misc_register(&migt_misc)",
        ),
        "drivers/mihw/Makefile": (
            "obj-$(CONFIG_MIGT) += migt.o",
        ),
        "include/linux/pkg_stat.h": (
            "int get_cur_render_uid(void);",
            "int migt_enable(void);",
            "int package_runtime_should_stop(void);",
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

    body = (root / "drivers/mihw/migt.c").read_text() if (root / "drivers/mihw/migt.c").is_file() else ""
    for token in (
        "/dev/metis",
        "core_ctl_set_boost",
        "cpufreq_register_notifier",
        "cpufreq_update_policy",
        "set_cpus_allowed_ptr",
        "iorap_dev",
        "return 0;\n\tdefault:",
    ):
        if token in body:
            failures.append("FORBIDDEN_STAGE7_FEATURE:" + token)

    return {
        "candidate": "0059",
        "stage": "bounded-legacy-migt-control",
        "target_ref": TARGET_REF,
        "donor_reference": DONOR_REF,
        "result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "claims": {
            "legacy_migt_device_source_present": True,
            "queue_dequeue_semantics_present": True,
            "ceiling_policy_ported": False,
            "boost_policy_active": False,
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

    print("CANDIDATE0059_STAGE7=" + report["result"])
    print("LEGACY_MIGT_DEVICE_SOURCE_PRESENT=true")
    print("QUEUE_DEQUEUE_SEMANTICS_PRESENT=true")
    print("CEILING_POLICY_PORTED=false")
    print("BOOST_POLICY_ACTIVE=false")
    print("METIS_COMPAT_ADDED=false")
    print("RUNTIME_TESTED=false")
    for item in report["failures"]:
        print("FAILURE=" + item)
    return 0 if report["result"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
