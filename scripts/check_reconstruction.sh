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

check "MI memory config" grep -q '^CONFIG_MI_MEMORY_SYSFS=m' "$CFG"
check "MI hardware id is built-in" grep -q '^CONFIG_MI_HARDWARE_ID=y' "$CFG"
check "MI thermal interface is module" grep -q '^CONFIG_MI_THERMAL_INTERFACE=m' "$CFG"
check "USB DTP is module" grep -q '^CONFIG_USB_F_DTP=m' "$CFG"
check "official lisa DTP ABI header" test -s include/linux/usb/f_dtp.h
check "DTP send-file ioctl ABI" grep -q '^#define DTP_SEND_FILE' include/linux/usb/f_dtp.h
check "DTP compat ABI" grep -q '^#define COMPAT_DTP_SEND_FILE' include/linux/usb/f_dtp.h
check "QGKI system enabled" grep -q '^CONFIG_QGKI_SYSTEM=y' "$CFG"
check "localversion auto enabled" grep -q '^CONFIG_LOCALVERSION_AUTO=y' "$CFG"
check "stock SCM suffix" sh -c "test \"$(cat .scmversion 2>/dev/null)\" = '-g5987d69e25da'"

check "mi-memory source" test -f drivers/misc/mi-memory/mem_interface.c
check "get_ufs_data provider" grep -q 'get_ufs_data' drivers/misc/mi-memory/mem_interface.c
check "get_ufs_hba_data provider" grep -q 'get_ufs_hba_data' drivers/misc/mi-memory/mem_interface.c
check "get_ufs_sdev_data provider" grep -q 'get_ufs_sdev_data' drivers/misc/mi-memory/mem_interface.c
check "memblock_mem_size_in_gb provider" grep -q 'memblock_mem_size_in_gb' drivers/misc/mi-memory/mem_interface.c
check "UFS hook declaration" grep -q 'extern void set_ufs_hba_data' drivers/scsi/ufs/ufshcd.c
check "UFS hook call" grep -q 'set_ufs_hba_data(sdev);' drivers/scsi/ufs/ufshcd.c
check "stock serial path avoids ufs_get_serial" sh -c "! grep -q 'ufs_get_serial' drivers/misc/mi-memory/mi_ufs_info.c"
check "stock serial path uses hba getter" grep -q 'get_ufs_hba_data' drivers/misc/mi-memory/mi_ufs_info.c
check "stock serial path uses string descriptor helper" grep -q 'ufs_get_string_desc' drivers/misc/mi-memory/mi_ufs_info.c

check "Goodix rawdata proc_ops" grep -q 'static const struct proc_ops rawdata_proc_fops' drivers/input/touchscreen/gt9897t/goodix_ts_core.c
check "Goodix lockdown proc_ops" grep -q 'static const struct proc_ops goodix_lockdown_info_ops' drivers/input/touchscreen/gt9897t/goodix_ts_core.c
check "Goodix firmware proc_ops" grep -q 'static const struct proc_ops goodix_fw_version_info_ops' drivers/input/touchscreen/gt9897t/goodix_ts_core.c
check "Goodix selftest proc_ops" grep -q 'static const struct proc_ops goodix_selftest_ops' drivers/input/touchscreen/gt9897t/goodix_ts_core.c
check "Goodix lisa macro spelling" sh -c "! grep -q 'CONFIG_BOARD_XAIOMI_LISA' drivers/input/touchscreen/gt9897t/goodix_ts_core.c"

check "mi-memory mv proc_ops" grep -q 'static const struct proc_ops mv_proc_fops' drivers/misc/mi-memory/mv.c
check "mi-memory type proc_ops" grep -q 'static const struct proc_ops memory_type_proc_fops' drivers/misc/mi-memory/mi_mem_type.c

check "MIUI audio ext clock preserved" sh -c "! grep -q 'afe_set_lpass_clk_cfg_ext_mclk' techpack/audio/asoc/codecs/audio-ext-clk-up.c"
check "MIUI WLAN mgmt SRNG TLV not imported" sh -c "! grep -q 'WMI_MGMT_SRNG_REAP_EVENTID' drivers/staging/fw-api/fw/wmi_tlv_defs.h"
check "MIUI WLAN MLO TID-map TLV not imported" sh -c "! grep -q 'WMI_MLO_PEER_TID_TO_LINK_MAP_EVENTID' drivers/staging/fw-api/fw/wmi_tlv_defs.h"

check "GLINK VERSION alias" grep -Eq '^#define[[:space:]]+GLINK_CMD_VERSION[[:space:]]+RPM_CMD_VERSION$' drivers/rpmsg/qcom_glink_native.c
check "GLINK OPEN alias" grep -Eq '^#define[[:space:]]+GLINK_CMD_OPEN[[:space:]]+RPM_CMD_OPEN$' drivers/rpmsg/qcom_glink_native.c
check "GLINK READ_NOTIFY alias" grep -Eq '^#define[[:space:]]+GLINK_CMD_READ_NOTIF[[:space:]]+RPM_CMD_READ_NOTIF$' drivers/rpmsg/qcom_glink_native.c

check "MI CNSS source" test -f drivers/net/wireless/mi_cnss_statistic/genl.c
check "CNSS wakeup export" grep -q 'cnss_statistic_wow_wakeup' drivers/net/wireless/mi_cnss_statistic/genl.c
check "MI CNSS config" grep -q '^CONFIG_MI_CNSS_STATISTIC=m' "$CFG"

exit "$fail"
