// SPDX-License-Identifier: GPL-2.0-only
/* Candidate0056: scoped Xiaomi battery-provider compatibility implementation.
 * Prototypes: target stock IKHEADERS include/linux/power_debug.h.
 * Capacity-mode semantics: public Xiaomi mi-power implementation, reference
 * LowTension/android_kernel_xiaomi_sm8475@39382bf, mi_power.c (lines 390-450).
 * This is not a full port of that platform's power/interrupt diagnostics.
 * No charging-current, voltage, thermal or authentication controls are added.
 */
#ifdef LISA_POWER_HOST_TEST
#include <stdbool.h>
#include <stddef.h>
#include <sys/types.h>
#define READ_ONCE(x) (x)
#define EXPORT_SYMBOL(x)
#else
#include <linux/device.h>
#include <linux/err.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/types.h>
#include <linux/lisa_power_compat.h>
#endif

/* Public implementation defaults raw gpower_mode to POWER_PERF_MODE (=1 in
 * target headers). Raw 0/1 select normal modes; raw 2/3/4 select save modes.
 */
static unsigned int lisa_power_mode = 1;
static bool lisa_power_debug_enable;

static bool lisa_power_mode_valid(unsigned long mode)
{
	return mode <= 4;
}

bool power_debug_print_enabled(void)
{
	return READ_ONCE(lisa_power_debug_enable);
}
EXPORT_SYMBOL(power_debug_print_enabled);

ssize_t mi_power_save_battery_cave(ssize_t capacity)
{
	unsigned int mode = READ_ONCE(lisa_power_mode);
	ssize_t result;

	/* Preserve unavailable/error and out-of-contract readings, never invent
	 * a battery or fabricate a fixed percentage when the driver has no data.
	 * Real percentage inputs in 0..100 follow the public mode-dependent curve.
	 */
	if (capacity < 0 || capacity > 100 || mode < 2)
		return capacity;
	if (capacity > 20)
		result = ((capacity - 20) * 100 + 106) / 107 + 25;
	else
		result = (capacity * 100 + 79) / 80;
	if (result > 100)
		result = 100;
	return result;
}
EXPORT_SYMBOL(mi_power_save_battery_cave);

#ifndef LISA_POWER_HOST_TEST
static ssize_t power_mode_show(struct class *cls,
		struct class_attribute *attr, char *buf)
{
	return scnprintf(buf, PAGE_SIZE, "%u\n", READ_ONCE(lisa_power_mode));
}

static ssize_t power_mode_store(struct class *cls,
		struct class_attribute *attr, const char *buf, size_t count)
{
	unsigned long value;
	int ret = kstrtoul(buf, 10, &value);

	if (ret)
		return ret;
	if (!lisa_power_mode_valid(value))
		return -EINVAL;
	WRITE_ONCE(lisa_power_mode, (unsigned int)value);
	return count;
}

static ssize_t debug_suspend_show(struct class *cls,
		struct class_attribute *attr, char *buf)
{
	return scnprintf(buf, PAGE_SIZE, "%u\n", power_debug_print_enabled());
}

static ssize_t debug_suspend_store(struct class *cls,
		struct class_attribute *attr, const char *buf, size_t count)
{
	unsigned long value;
	int ret = kstrtoul(buf, 10, &value);

	if (ret)
		return ret;
	if (value > 1)
		return -EINVAL;
	WRITE_ONCE(lisa_power_debug_enable, value != 0);
	return count;
}

static struct class_attribute class_attr_power_mode =
	__ATTR(power_mode, 0664, power_mode_show, power_mode_store);
static struct class_attribute class_attr_debug_suspend =
	__ATTR(debug_suspend, 0644, debug_suspend_show, debug_suspend_store);

static int __init lisa_power_compat_init(void)
{
	struct class *cls;
	int ret;

	cls = class_create(THIS_MODULE, "power_debug");
	if (IS_ERR(cls))
		return PTR_ERR(cls);
	ret = class_create_file(cls, &class_attr_power_mode);
	if (ret)
		goto destroy;
	ret = class_create_file(cls, &class_attr_debug_suspend);
	if (ret) {
		class_remove_file(cls, &class_attr_power_mode);
		goto destroy;
	}
	pr_info("LISA0056_POWER_COMPAT ready=1 mode=%u scope=battery_provider\n",
		READ_ONCE(lisa_power_mode));
	return 0;
destroy:
	class_destroy(cls);
	return ret;
}
subsys_initcall(lisa_power_compat_init);
#endif
