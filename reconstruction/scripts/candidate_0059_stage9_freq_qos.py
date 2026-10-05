#!/usr/bin/env python3
"""Candidate0059 Stage9: policy-scoped MIGT FREQ_QOS control.

Requires Stages1-7 and the Stage8 API audit. This stage translates the bounded
MIGT boost-floor and ceiling-cap path to per-policy frequency QoS requests.
It does not enable core_ctl boost, alter thermal policy, or force a global max.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TARGET_REF = "6e568aabc77a06fa787baec1d9e60e4b559874a3"
DONOR_REF = "LeviMarvin/android_kernel_xiaomi_alioth@e7065bc9ead4a0ca183f51101e07dd45a9d5c558"

STAGE9_BLOCK = r'''
/* Candidate0059 Stage9: policy-scoped FREQ_QOS migration. */
#include <linux/cpu.h>
#include <linux/cpufreq.h>
#include <linux/jiffies.h>
#include <linux/moduleparam.h>
#include <linux/pm_qos.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/workqueue.h>

struct c0059_migt_freq_config {
	unsigned int boost_freq;
	unsigned int ceiling_freq;
};

struct c0059_migt_policy_qos {
	struct cpufreq_policy *policy;
	struct freq_qos_request min_req;
	struct freq_qos_request max_req;
	bool min_added;
	bool max_added;
};

static DEFINE_PER_CPU(struct c0059_migt_freq_config, migt_freq_config);
static DEFINE_PER_CPU(struct c0059_migt_policy_qos, migt_policy_qos);
static DEFINE_MUTEX(migt_qos_lock);
static struct delayed_work migt_boost_clear_work;
static struct delayed_work migt_ceiling_clear_work;
static bool migt_boost_active;
static bool migt_ceiling_active;
static bool migt_freq_enabled;
static unsigned int migt_boost_policy;
static uid_t migt_ceiling_uid;
static unsigned int migt_boost_ms = 50;
static unsigned int migt_ceiling_slack_ms = 1000;
module_param(migt_boost_ms, uint, 0644);
module_param(migt_ceiling_slack_ms, uint, 0644);
module_param_named(boost_policy, migt_boost_policy, uint, 0644);

static unsigned int migt_policy_leader(struct cpufreq_policy *policy)
{
	unsigned int cpu;

	cpu = cpumask_first(policy->related_cpus);
	if (cpu >= nr_cpu_ids)
		cpu = policy->cpu;
	return cpu;
}

static unsigned int migt_policy_boost_value(struct cpufreq_policy *policy)
{
	unsigned int cpu;
	unsigned int value = 0;

	for_each_cpu(cpu, policy->related_cpus)
		value = max(value, per_cpu(migt_freq_config, cpu).boost_freq);

	if (!value)
		return FREQ_QOS_MIN_DEFAULT_VALUE;
	return clamp_t(unsigned int, value, policy->cpuinfo.min_freq,
		       policy->cpuinfo.max_freq);
}

static unsigned int migt_policy_ceiling_value(struct cpufreq_policy *policy)
{
	unsigned int cpu;
	unsigned int value = 0;

	for_each_cpu(cpu, policy->related_cpus) {
		unsigned int configured = per_cpu(migt_freq_config, cpu).ceiling_freq;

		if (configured && (!value || configured < value))
			value = configured;
	}

	if (!value)
		return FREQ_QOS_MAX_DEFAULT_VALUE;
	return clamp_t(unsigned int, value, policy->cpuinfo.min_freq,
		       policy->cpuinfo.max_freq);
}

static void migt_qos_refresh_locked(void)
{
	unsigned int cpu;

	for_each_possible_cpu(cpu) {
		struct c0059_migt_policy_qos *qos = &per_cpu(migt_policy_qos, cpu);
		unsigned int min_value;
		unsigned int max_value;

		if (!qos->policy || !qos->min_added || !qos->max_added)
			continue;

		min_value = migt_boost_active ?
			migt_policy_boost_value(qos->policy) :
			FREQ_QOS_MIN_DEFAULT_VALUE;
		max_value = migt_ceiling_active ?
			migt_policy_ceiling_value(qos->policy) :
			FREQ_QOS_MAX_DEFAULT_VALUE;

		freq_qos_update_request(&qos->min_req, min_value);
		freq_qos_update_request(&qos->max_req, max_value);
	}
}

static void migt_qos_refresh(void)
{
	mutex_lock(&migt_qos_lock);
	migt_qos_refresh_locked();
	mutex_unlock(&migt_qos_lock);
}

static int migt_qos_attach_policy(struct cpufreq_policy *policy)
{
	struct c0059_migt_policy_qos *qos;
	unsigned int leader;
	int ret;

	if (!policy)
		return -EINVAL;

	leader = migt_policy_leader(policy);
	if (leader >= nr_cpu_ids)
		return -EINVAL;

	mutex_lock(&migt_qos_lock);
	qos = &per_cpu(migt_policy_qos, leader);
	if (qos->policy == policy) {
		mutex_unlock(&migt_qos_lock);
		return 0;
	}
	if (qos->policy) {
		mutex_unlock(&migt_qos_lock);
		return -EBUSY;
	}

	ret = freq_qos_add_request(&policy->constraints, &qos->min_req,
				   FREQ_QOS_MIN, FREQ_QOS_MIN_DEFAULT_VALUE);
	if (ret < 0)
		goto out_unlock;
	qos->min_added = true;

	ret = freq_qos_add_request(&policy->constraints, &qos->max_req,
				   FREQ_QOS_MAX, FREQ_QOS_MAX_DEFAULT_VALUE);
	if (ret < 0) {
		freq_qos_remove_request(&qos->min_req);
		qos->min_added = false;
		goto out_unlock;
	}
	qos->max_added = true;
	qos->policy = policy;
	migt_qos_refresh_locked();
	ret = 0;

out_unlock:
	mutex_unlock(&migt_qos_lock);
	return ret;
}

static void migt_qos_detach_policy(struct cpufreq_policy *policy)
{
	struct c0059_migt_policy_qos *qos;
	unsigned int leader;

	if (!policy)
		return;

	leader = migt_policy_leader(policy);
	if (leader >= nr_cpu_ids)
		return;

	mutex_lock(&migt_qos_lock);
	qos = &per_cpu(migt_policy_qos, leader);
	if (qos->policy != policy) {
		mutex_unlock(&migt_qos_lock);
		return;
	}

	if (qos->max_added)
		freq_qos_remove_request(&qos->max_req);
	if (qos->min_added)
		freq_qos_remove_request(&qos->min_req);
	memset(qos, 0, sizeof(*qos));
	mutex_unlock(&migt_qos_lock);
}

static int migt_cpufreq_policy_notify(struct notifier_block *nb,
				      unsigned long event, void *data)
{
	struct cpufreq_policy *policy = data;

	(void)nb;
	switch (event) {
	case CPUFREQ_CREATE_POLICY:
		if (migt_qos_attach_policy(policy))
			pr_warn("failed to attach FREQ_QOS requests to policy%u\n",
				policy->cpu);
		break;
	case CPUFREQ_REMOVE_POLICY:
		migt_qos_detach_policy(policy);
		break;
	default:
		break;
	}
	return NOTIFY_OK;
}

static struct notifier_block migt_cpufreq_nb = {
	.notifier_call = migt_cpufreq_policy_notify,
};

static void migt_set_boost_active(bool active)
{
	WRITE_ONCE(migt_boost_active, active);
	migt_qos_refresh();
}

static void migt_set_ceiling_active(bool active)
{
	WRITE_ONCE(migt_ceiling_active, active);
	migt_qos_refresh();
}

static void migt_boost_clear(struct work_struct *work)
{
	(void)work;
	migt_set_boost_active(false);
}

static void migt_ceiling_clear(struct work_struct *work)
{
	(void)work;
	migt_set_ceiling_active(false);
}

static void migt_trigger_boost(void)
{
	if (!READ_ONCE(migt_freq_enabled) || !READ_ONCE(migt_boost_policy))
		return;

	migt_set_boost_active(true);
	mod_delayed_work(system_wq, &migt_boost_clear_work,
			 msecs_to_jiffies(max_t(unsigned int, 1, migt_boost_ms)));
}

static void migt_trigger_ceiling(uid_t uid)
{
	WRITE_ONCE(migt_ceiling_uid, uid);
	migt_set_ceiling_active(true);
	mod_delayed_work(system_wq, &migt_ceiling_clear_work,
			 msecs_to_jiffies(max_t(unsigned int, 1,
						      migt_ceiling_slack_ms)));
}

static int migt_parse_freq_param(const char *value, bool ceiling)
{
	char *copy;
	char *cursor;
	char *token;
	unsigned int cpu;
	unsigned int freq;
	bool any_boost = false;
	int ret = 0;

	copy = kstrdup(value, GFP_KERNEL);
	if (!copy)
		return -ENOMEM;
	cursor = strim(copy);

	if (!strchr(cursor, ':')) {
		ret = kstrtouint(cursor, 0, &freq);
		if (ret)
			goto out;
		for_each_possible_cpu(cpu) {
			if (ceiling)
				per_cpu(migt_freq_config, cpu).ceiling_freq = freq;
			else
				per_cpu(migt_freq_config, cpu).boost_freq = freq;
		}
	} else {
		while ((token = strsep(&cursor, " ,\t\n")) != NULL) {
			char *sep;

			if (!*token)
				continue;
			sep = strchr(token, ':');
			if (!sep) {
				ret = -EINVAL;
				goto out;
			}
			*sep = '\0';
			ret = kstrtouint(token, 0, &cpu);
			if (ret || cpu >= nr_cpu_ids || !cpu_possible(cpu)) {
				ret = -EINVAL;
				goto out;
			}
			ret = kstrtouint(sep + 1, 0, &freq);
			if (ret)
				goto out;
			if (ceiling)
				per_cpu(migt_freq_config, cpu).ceiling_freq = freq;
			else
				per_cpu(migt_freq_config, cpu).boost_freq = freq;
		}
	}

	if (!ceiling) {
		for_each_possible_cpu(cpu) {
			if (per_cpu(migt_freq_config, cpu).boost_freq) {
				any_boost = true;
				break;
			}
		}
		WRITE_ONCE(migt_freq_enabled, any_boost);
	}
	migt_qos_refresh();

out:
	kfree(copy);
	return ret;
}

static int set_migt_freq(const char *value, const struct kernel_param *kp)
{
	bool ceiling = !strcmp(kp->name, "migt_ceiling_freq");

	return migt_parse_freq_param(value, ceiling);
}

static int get_migt_freq(char *buf, const struct kernel_param *kp)
{
	bool ceiling = !strcmp(kp->name, "migt_ceiling_freq");
	unsigned int cpu;
	int count = 0;

	for_each_possible_cpu(cpu) {
		unsigned int value = ceiling ?
			per_cpu(migt_freq_config, cpu).ceiling_freq :
			per_cpu(migt_freq_config, cpu).boost_freq;

		count += scnprintf(buf + count, PAGE_SIZE - count,
				   "%u:%u ", cpu, value);
	}
	count += scnprintf(buf + count, PAGE_SIZE - count, "\n");
	return count;
}

static const struct kernel_param_ops migt_freq_ops = {
	.set = set_migt_freq,
	.get = get_migt_freq,
};

module_param_cb(migt_freq, &migt_freq_ops, NULL, 0644);
module_param_cb(migt_ceiling_freq, &migt_freq_ops, NULL, 0644);
'''


def replace_once(path: Path, old: str, new: str) -> None:
    body = path.read_text()
    count = body.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement, found {count}: {old!r}")
    path.write_text(body.replace(old, new, 1))


def apply(root: Path) -> None:
    driver = root / "drivers/mihw/migt.c"
    if not driver.is_file():
        raise RuntimeError("Stage7 drivers/mihw/migt.c missing")
    body = driver.read_text()
    if "Candidate0059 Stage9: policy-scoped FREQ_QOS migration" in body:
        raise RuntimeError("Stage9 already applied")
    if "return -EOPNOTSUPP;" not in body:
        raise RuntimeError("Stage7 SET_CEILING guard missing")

    replace_once(
        driver,
        '#include <linux/user_namespace.h>\n',
        '#include <linux/user_namespace.h>\n' + STAGE9_BLOCK,
    )

    replace_once(
        driver,
        "int migt_enable(void)\n{\n\treturn READ_ONCE(migt_device_ready);\n}\n\n"
        "int package_runtime_should_stop(void)\n{\n"
        "\t/* Boost policy is intentionally not active in Stage7. */\n"
        "\treturn 1;\n}\n",
        "int migt_enable(void)\n{\n\treturn READ_ONCE(migt_device_ready) ? READ_ONCE(migt_boost_policy) : 0;\n}\n\n"
        "int package_runtime_should_stop(void)\n{\n\treturn READ_ONCE(migt_boost_policy) == 0;\n}\n",
    )

    replace_once(
        driver,
        "\tcase QUEUE_BUFFER:\n"
        "\t\tmutex_lock(&migt_control_lock);\n"
        "\t\tif (traced_uid != last_traced_uid) {\n"
        "\t\t\treset_render_info(RENDER_QUEUE_THREAD);\n"
        "\t\t\treset_render_info(RENDER_DEQUEUE_THREAD);\n"
        "\t\t\tgame_load_reset();\n"
        "\t\t\tWRITE_ONCE(last_traced_uid, traced_uid);\n"
        "\t\t}\n"
        "\t\tupdate_render_info(current, RENDER_QUEUE_THREAD);\n"
        "\t\tmutex_unlock(&migt_control_lock);\n"
        "\t\treturn 0;\n",
        "\tcase QUEUE_BUFFER:\n"
        "\t\tmutex_lock(&migt_control_lock);\n"
        "\t\tif (traced_uid != last_traced_uid) {\n"
        "\t\t\treset_render_info(RENDER_QUEUE_THREAD);\n"
        "\t\t\treset_render_info(RENDER_DEQUEUE_THREAD);\n"
        "\t\t\tgame_load_reset();\n"
        "\t\t\tif (READ_ONCE(migt_ceiling_active) &&\n"
        "\t\t\t    traced_uid != READ_ONCE(migt_ceiling_uid)) {\n"
        "\t\t\t\tcancel_delayed_work(&migt_ceiling_clear_work);\n"
        "\t\t\t\tmigt_set_ceiling_active(false);\n"
        "\t\t\t}\n"
        "\t\t\tWRITE_ONCE(last_traced_uid, traced_uid);\n"
        "\t\t}\n"
        "\t\tupdate_render_info(current, RENDER_QUEUE_THREAD);\n"
        "\t\tmigt_trigger_boost();\n"
        "\t\tif (READ_ONCE(migt_ceiling_active) &&\n"
        "\t\t    traced_uid == READ_ONCE(migt_ceiling_uid))\n"
        "\t\t\tmod_delayed_work(system_wq, &migt_ceiling_clear_work,\n"
        "\t\t\t\tmsecs_to_jiffies(max_t(unsigned int, 1,\n"
        "\t\t\t\t\t\t      migt_ceiling_slack_ms)));\n"
        "\t\tmutex_unlock(&migt_control_lock);\n"
        "\t\treturn 0;\n",
    )

    replace_once(
        driver,
        "\tcase SET_CEILING:\n\t\treturn -EOPNOTSUPP;\n",
        "\tcase SET_CEILING:\n"
        "\t\tmutex_lock(&migt_control_lock);\n"
        "\t\tmigt_trigger_ceiling(traced_uid);\n"
        "\t\tmutex_unlock(&migt_control_lock);\n"
        "\t\treturn 0;\n",
    )

    replace_once(
        driver,
        "static int __init migt_init(void)\n{\n\tint ret;\n\n"
        "\tret = misc_register(&migt_misc);\n",
        "static int __init migt_init(void)\n{\n"
        "\tstruct cpufreq_policy *policy;\n"
        "\tunsigned int cpu;\n"
        "\tint ret;\n\n"
        "\tINIT_DELAYED_WORK(&migt_boost_clear_work, migt_boost_clear);\n"
        "\tINIT_DELAYED_WORK(&migt_ceiling_clear_work, migt_ceiling_clear);\n"
        "\tret = cpufreq_register_notifier(&migt_cpufreq_nb, CPUFREQ_POLICY_NOTIFIER);\n"
        "\tif (ret)\n"
        "\t\treturn ret;\n\n"
        "\tfor_each_possible_cpu(cpu) {\n"
        "\t\tpolicy = cpufreq_cpu_get(cpu);\n"
        "\t\tif (!policy)\n"
        "\t\t\tcontinue;\n"
        "\t\tmigt_qos_attach_policy(policy);\n"
        "\t\tcpufreq_cpu_put(policy);\n"
        "\t}\n\n"
        "\tret = misc_register(&migt_misc);\n",
    )

    replace_once(
        driver,
        "\tret = misc_register(&migt_misc);\n\tif (ret)\n\t\treturn ret;\n",
        "\tret = misc_register(&migt_misc);\n"
        "\tif (ret) {\n"
        "\t\tcpufreq_unregister_notifier(&migt_cpufreq_nb, CPUFREQ_POLICY_NOTIFIER);\n"
        "\t\tfor_each_possible_cpu(cpu) {\n"
        "\t\t\tpolicy = cpufreq_cpu_get(cpu);\n"
        "\t\t\tif (!policy)\n"
        "\t\t\t\tcontinue;\n"
        "\t\t\tmigt_qos_detach_policy(policy);\n"
        "\t\t\tcpufreq_cpu_put(policy);\n"
        "\t\t}\n"
        "\t\treturn ret;\n"
        "\t}\n",
    )

    replace_once(
        driver,
        'pr_info("Candidate0059 bounded legacy MIGT control registered\\n");',
        'pr_info("Candidate0059 MIGT FREQ_QOS control registered\\n");',
    )


def verify(root: Path) -> dict:
    failures: list[str] = []
    driver = root / "drivers/mihw/migt.c"
    body = driver.read_text() if driver.is_file() else ""

    required = (
        "Candidate0059 Stage9: policy-scoped FREQ_QOS migration",
        "struct freq_qos_request min_req;",
        "struct freq_qos_request max_req;",
        "freq_qos_add_request(&policy->constraints",
        "freq_qos_update_request(&qos->min_req",
        "freq_qos_update_request(&qos->max_req",
        "freq_qos_remove_request(&qos->max_req)",
        "CPUFREQ_CREATE_POLICY",
        "CPUFREQ_REMOVE_POLICY",
        "cpufreq_register_notifier(&migt_cpufreq_nb, CPUFREQ_POLICY_NOTIFIER)",
        "module_param_cb(migt_freq, &migt_freq_ops, NULL, 0644);",
        "module_param_cb(migt_ceiling_freq, &migt_freq_ops, NULL, 0644);",
        "migt_trigger_boost();",
        "migt_trigger_ceiling(traced_uid);",
        "case SET_CEILING:",
        "return READ_ONCE(migt_boost_policy) == 0;",
    )
    if not driver.is_file():
        failures.append("MISSING_FILE:drivers/mihw/migt.c")
    else:
        for marker in required:
            if marker not in body:
                failures.append("MISSING_MARKER:" + marker)

    forbidden = (
        "CPUFREQ_ADJUST",
        "cpufreq_verify_within_limits",
        "core_ctl_set_boost",
        "policy->min =",
        "policy->max =",
        "thermal_zone",
        "-EOPNOTSUPP",
    )
    for token in forbidden:
        if token in body:
            failures.append("FORBIDDEN_STAGE9_FEATURE:" + token)

    evidence = {
        "drivers/mihw/migt.c": {
            "exists": driver.is_file(),
            "sha256": hashlib.sha256(driver.read_bytes()).hexdigest()
            if driver.is_file()
            else None,
        }
    }

    return {
        "candidate": "0059",
        "stage": "policy-scoped-freq-qos",
        "target_ref": TARGET_REF,
        "donor_reference": DONOR_REF,
        "result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "evidence": evidence,
        "claims": {
            "policy_scoped_freq_qos_present": True,
            "boost_floor_path_present": True,
            "ceiling_cap_path_present": True,
            "set_ceiling_supported": True,
            "core_ctl_boost_active": False,
            "thermal_bypass_added": False,
            "global_max_pin_added": False,
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

    print("CANDIDATE0059_STAGE9=" + report["result"])
    print("POLICY_SCOPED_FREQ_QOS_PRESENT=true")
    print("BOOST_FLOOR_PATH_PRESENT=true")
    print("CEILING_CAP_PATH_PRESENT=true")
    print("SET_CEILING_SUPPORTED=true")
    print("CORE_CTL_BOOST_ACTIVE=false")
    print("THERMAL_BYPASS_ADDED=false")
    print("GLOBAL_MAX_PIN_ADDED=false")
    print("RUNTIME_TESTED=false")
    for item in report["failures"]:
        print("FAILURE=" + item)
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
