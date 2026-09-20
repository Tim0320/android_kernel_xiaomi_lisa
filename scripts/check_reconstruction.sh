#!/usr/bin/env bash
set -euo pipefail

fail=0
check() {
    local name="$1"
    shift
    if "$@"; then
        printf 'PASS  %s\n' "$name"
    else
        printf 'FAIL  %s\n' "$name" >&2
        fail=1
    fi
}

CFG=arch/arm64/configs/vendor/lisa_QGKI.config

check "Linux 5.4.289" sh -c "grep -q '^VERSION = 5$' Makefile && grep -q '^PATCHLEVEL = 4$' Makefile && grep -q '^SUBLEVEL = 289$' Makefile"
check "lisa QGKI config" test -f "$CFG"
check "SM7325 pinctrl" grep -q '^CONFIG_PINCTRL_SM7325=y' "$CFG"
check "Goodix BRL" grep -q '^CONFIG_TOUCHSCREEN_GOODIX_BRL=m' "$CFG"
check "Xiaomi touchfeature" grep -q '^CONFIG_TOUCHSCREEN_XIAOMI_TOUCHFEATURE=m' "$CFG"
check "QCA6750 CNSS" grep -q '^CONFIG_CNSS_QCA6750=y' "$CFG"
check "mi-memory source" test -f drivers/misc/mi-memory/mem_interface.c
check "get_ufs_data provider" grep -q 'get_ufs_data' drivers/misc/mi-memory/mem_interface.c
check "get_ufs_hba_data provider" grep -q 'get_ufs_hba_data' drivers/misc/mi-memory/mem_interface.c
check "get_ufs_sdev_data provider" grep -q 'get_ufs_sdev_data' drivers/misc/mi-memory/mem_interface.c
check "memblock_mem_size_in_gb provider" grep -q 'memblock_mem_size_in_gb' drivers/misc/mi-memory/mem_interface.c
check "UFS hook declaration" grep -q 'extern void set_ufs_hba_data' drivers/scsi/ufs/ufshcd.c
check "UFS hook call" grep -q 'set_ufs_hba_data(sdev);' drivers/scsi/ufs/ufshcd.c
check "MI memory config" grep -q '^CONFIG_MI_MEMORY_SYSFS=m' "$CFG"
check "MI CNSS source" test -f drivers/net/wireless/mi_cnss_statistic/genl.c
check "CNSS wakeup export" grep -q 'cnss_statistic_wow_wakeup' drivers/net/wireless/mi_cnss_statistic/genl.c
check "MI CNSS config" grep -q '^CONFIG_MI_CNSS_STATISTIC=m' "$CFG"

exit "$fail"
