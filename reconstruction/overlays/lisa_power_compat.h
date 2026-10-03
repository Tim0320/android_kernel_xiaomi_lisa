/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _LINUX_LISA_POWER_COMPAT_H
#define _LINUX_LISA_POWER_COMPAT_H
#include <linux/types.h>
bool power_debug_print_enabled(void);
ssize_t mi_power_save_battery_cave(ssize_t capacity);
#endif
