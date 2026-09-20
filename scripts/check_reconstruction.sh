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
check "VA macro has 5.4.289 mclk state" grep -q 'u32 mclk_freq;' techpack/audio/asoc/codecs/bolero/va-macro.c
check "VA macro has 5.4.289 device state" grep -q 'bool dev_up;' techpack/audio/asoc/codecs/bolero/va-macro.c
check "Goodix uses proc_ops" grep -q 'static const struct proc_ops rawdata_proc_fops' drivers/input/touchscreen/gt9897t/goodix_ts_core.c
check "Goodix lisa macro spelling" sh -c "! grep -q 'CONFIG_BOARD_XAIOMI_LISA' drivers/input/touchscreen/gt9897t/goodix_ts_core.c"
check "MI memory config" grep -q '^CONFIG_MI_MEMORY_SYSFS=m' "$CFG"
check "MI hardware id is module" grep -q '^CONFIG_MI_HARDWARE_ID=m' "$CFG"
check "MI thermal interface is module" grep -q '^CONFIG_MI_THERMAL_INTERFACE=m' "$CFG"
check "USB DTP is module" grep -q '^CONFIG_USB_F_DTP=m' "$CFG"
check "QGKI system enabled" grep -q '^CONFIG_QGKI_SYSTEM=y' "$CFG"
check "localversion auto enabled" grep -q '^CONFIG_LOCALVERSION_AUTO=y' "$CFG"
check "stock SCM suffix" sh -c "test \"$(cat .scmversion 2>/dev/null)\" = '-g5987d69e25da'"
check "stock serial path avoids ufs_get_serial" sh -c "! grep -q 'ufs_get_serial' drivers/misc/mi-memory/mi_ufs_info.c"
check "stock serial path uses hba getter" grep -q 'get_ufs_hba_data' drivers/misc/mi-memory/mi_ufs_info.c
check "stock serial path uses string descriptor helper" grep -q 'ufs_get_string_desc' drivers/misc/mi-memory/mi_ufs_info.c
check "MI CNSS source" test -f drivers/net/wireless/mi_cnss_statistic/genl.c
check "CNSS wakeup export" grep -q 'cnss_statistic_wow_wakeup' drivers/net/wireless/mi_cnss_statistic/genl.c
check "MI CNSS config" grep -q '^CONFIG_MI_CNSS_STATISTIC=m' "$CFG"

exit "$fail"
