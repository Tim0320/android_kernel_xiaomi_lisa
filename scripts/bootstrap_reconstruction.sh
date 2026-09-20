#!/usr/bin/env bash
set -euo pipefail

META_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$META_ROOT/reconstruction/manifest.env"

WORK_ROOT="${RUNNER_TEMP:-/tmp}/lisa-reconstruction"
SRC="$WORK_ROOT/kernel"
rm -rf "$WORK_ROOT"
mkdir -p "$WORK_ROOT"

echo "::group::Clone MIUI lisa-capable base"
git clone --filter=blob:none --single-branch --branch "$BASE_REF" "$BASE_REPO" "$SRC"
cd "$SRC"
git config user.name "lisa-reconstruction"
git config user.email "actions@users.noreply.github.com"
echo "::endgroup::"

echo "::group::Merge Qualcomm/Android 5.4.289 downstream"
git remote add stable "$STABLE_REPO"
git fetch --filter=blob:none stable "$STABLE_COMMIT"
BASE_SHA="$(git rev-parse HEAD)"
if ! git merge --no-edit --no-ff -X ours "$STABLE_COMMIT"; then
    mapfile -t unresolved < <(git diff --name-only --diff-filter=U)
    printf 'Stable merge unresolved files:\n%s\n' "${unresolved[*]}" >&2

    # Known Qualcomm audio conflict: the MIUI lisa-capable baseline intentionally
    # removed msm-pcm-routing-auto.c. Preserve that deletion instead of
    # resurrecting the obsolete routing implementation from the stable donor.
    for path in "${unresolved[@]}"; do
        case "$path" in
            techpack/audio/asoc/msm-pcm-routing-auto.c)
                git rm -f -- "$path"
                ;;
            *)
                echo "Unhandled stable merge conflict: $path" >&2
                exit 30
                ;;
        esac
    done

    git commit --no-edit
fi
printf '%s\n' "$BASE_SHA" > "$WORK_ROOT/base-before-stable.txt"
echo "::endgroup::"

echo "::group::Repair known semantic merge mismatches"
# va-macro gained dev_up/mclk_freq handling as a coherent 5.4.289 update.
# A hunk-level merge can leave new uses with the old struct definition, so
# take this common Qualcomm audio file atomically from the 5.4.289 source.
git checkout "$STABLE_COMMIT" -- techpack/audio/asoc/codecs/bolero/va-macro.c

# The lisa Goodix source predates the proc_ops backport in the 5.4.289 common
# core and also carries a misspelled board macro around DT local variables.
python3 - <<'PY'
from pathlib import Path

path = Path("drivers/input/touchscreen/gt9897t/goodix_ts_core.c")
text = path.read_text()

old_ops = """static const struct file_operations rawdata_proc_fops = {
	.open = rawdata_proc_open,
	.read = seq_read,
	.llseek = seq_lseek,
	.release = single_release,
};"""
new_ops = """static const struct proc_ops rawdata_proc_fops = {
	.proc_open = rawdata_proc_open,
	.proc_read = seq_read,
	.proc_lseek = seq_lseek,
	.proc_release = single_release,
};"""
if old_ops not in text:
    raise SystemExit("Goodix rawdata file_operations block not found")
text = text.replace(old_ops, new_ops, 1)

proc_replacements = {
"""static const struct file_operations goodix_lockdown_info_ops = {
	.read = goodix_lockdown_info_read,
};""":
"""static const struct proc_ops goodix_lockdown_info_ops = {
	.proc_read = goodix_lockdown_info_read,
};""",

"""static const struct file_operations goodix_fw_version_info_ops = {
	.read = goodix_fw_version_info_read,
};""":
"""static const struct proc_ops goodix_fw_version_info_ops = {
	.proc_read = goodix_fw_version_info_read,
};""",

"""static const struct file_operations goodix_selftest_ops = {
	.read = goodix_selftest_read,
	.write = goodix_selftest_write,
};""":
"""static const struct proc_ops goodix_selftest_ops = {
	.proc_read = goodix_selftest_read,
	.proc_write = goodix_selftest_write,
};""",
}
for old, new in proc_replacements.items():
    if old not in text:
        raise SystemExit(f"Goodix procfs operations block not found: {old.splitlines()[0]}")
    text = text.replace(old, new, 1)

if "CONFIG_BOARD_XAIOMI_LISA" not in text:
    raise SystemExit("Goodix misspelled lisa board macro not found")
text = text.replace("CONFIG_BOARD_XAIOMI_LISA", "CONFIG_BOARD_XIAOMI_LISA")

path.write_text(text)

# The MIUI TFA98xx source has whitespace that Clang 11 diagnoses as
# -Wmisleading-indentation under the QGKI -Werror build. Keep the original
# one-shot reset semantics, but make the scope explicit.
path = Path("techpack/audio/asoc/codecs/tfa98xx/src/tfa98xx.c")
text = path.read_text()
old = """    if (0 == tfa98xx_device_count)
    	tfa98xx_ext_reset(tfa98xx);"""
new = """    if (0 == tfa98xx_device_count) {
    	tfa98xx_ext_reset(tfa98xx);
    }"""
if old not in text:
    raise SystemExit("TFA98xx reset indentation block not found")
text = text.replace(old, new, 1)
path.write_text(text)

# Restore the coherent 5.4.289 WCD937x EAR POST_PMD hunk. The merge can keep
# the newer PRE_PMD status-mask logic while dropping the matching closing
# brace/cleanup sequence, which makes following functions parse as nested.
path = Path("techpack/audio/asoc/codecs/wcd937x/wcd937x.c")
text = path.read_text()
old = """		else {
			snd_soc_component_update_bits(component,
					WCD937X_DIGITAL_PDM_WD_CTL0,
					0x17, 0x00);
		break;
	};"""
new = """		else {
			snd_soc_component_update_bits(component,
					WCD937X_DIGITAL_PDM_WD_CTL0,
					0x17, 0x00);
			clear_bit(WCD_EAR_EN, &wcd937x->status_mask);
		}
		usleep_range(10000, 10010);
		/* disable EAR CnP FSM */
		snd_soc_component_update_bits(component,
					WCD937X_EAR_EAR_EN_REG,
					0x02, 0x00);
		/* toggle EAR PA to let PA control registers take effect */
		snd_soc_component_update_bits(component,
					WCD937X_ANA_EAR,
					0x80, 0x80);
		snd_soc_component_update_bits(component,
					WCD937X_ANA_EAR,
					0x80, 0x00);
		/* enable EAR CnP FSM */
		snd_soc_component_update_bits(component,
					WCD937X_EAR_EAR_EN_REG,
					0x02, 0x02);
		break;
	};"""
if old not in text:
    raise SystemExit("WCD937x broken EAR POST_PMD merge block not found")
text = text.replace(old, new, 1)
path.write_text(text)
PY
echo "::endgroup::"

echo "::group::Remove non-stock KernelSU integration"
# The MIUI donor tracks KernelSU as an optional third-party submodule through
# drivers/kernelsu -> ../KernelSU/kernel. Stock HyperOS lisa does not require
# this integration, and keeping the broken symlink makes Kconfig fail before
# the real kernel build starts.
sed -i '/source "drivers\/kernelsu\/Kconfig"/d' drivers/Kconfig
sed -i '/CONFIG_KSU.*kernelsu\//d' drivers/Makefile
rm -f drivers/kernelsu
rm -rf KernelSU
echo "::endgroup::"

if ! grep -q '^VERSION = 5$' Makefile; then
    echo "Expected VERSION=5 after stable merge." >&2
    head -n 8 Makefile >&2
    exit 31
fi
if ! grep -q '^PATCHLEVEL = 4$' Makefile; then
    echo "Expected PATCHLEVEL=4 after stable merge." >&2
    head -n 8 Makefile >&2
    exit 31
fi
if ! grep -q '^SUBLEVEL = 289$' Makefile; then
    echo "Expected SUBLEVEL=289 after stable merge." >&2
    head -n 8 Makefile >&2
    exit 31
fi

echo "::group::Import Xiaomi mi-memory"
git clone --depth=1 --branch "$MI_MEMORY_REF" "$MI_MEMORY_REPO" "$WORK_ROOT/mi-memory"
rm -rf drivers/misc/mi-memory
cp -a "$WORK_ROOT/mi-memory/drivers/misc/mi-memory" drivers/misc/mi-memory

# Keep the complete 5.4 donor implementation because its UFS helper calls
# match the Lahaina/Yupik 4-argument ufshcd_read_string_desc API. Align only
# the exported memory-size ABI with the stock lisa module evidence.
python3 - <<'PY'
from pathlib import Path

patches = {
    Path("drivers/misc/mi-memory/mem_interface.c"): [
        ("double memblock_mem_size_in_gb(void)", "u8 memblock_mem_size_in_gb(void)"),
        (
            "return (double)((memblock_phys_mem_size() + memblock_reserved_size()) / (double)1024/1024/1024);",
            "return (u8)((memblock_phys_mem_size() + memblock_reserved_size()) / 1024 / 1024 / 1024);",
        ),
    ],
    Path("drivers/misc/mi-memory/mem_interface.h"): [
        ("double memblock_mem_size_in_gb(void);", "u8 memblock_mem_size_in_gb(void);"),
    ],
    Path("drivers/misc/mi-memory/mi_dram_info.c"): [
        ("double ddr_size_in_GB = 0;", "u8 ddr_size_in_GB = 0;"),
        (
            'pr_err("memblock_mem_size %f\\n", ddr_size_in_GB);',
            'pr_err("memblock_mem_size %d\\n", ddr_size_in_GB);',
        ),
    ],
}

for path, replacements in patches.items():
    text = path.read_text()
    for old, new in replacements:
        if old not in text:
            raise SystemExit(f"expected donor pattern missing in {path}: {old}")
        text = text.replace(old, new, 1)
    path.write_text(text)

# Stock mi_memory.ko does not import ufs_get_serial(). Its serial sysfs path
# calls get_ufs_hba_data() and the exported hba-aware ufs_get_string_desc().
path = Path("drivers/misc/mi-memory/mi_ufs_info.c")
text = path.read_text()
if "DEVICE_DESC_PARAM_FEAT_SUP" not in text:
    raise SystemExit("mi-memory donor UFS feature field name not found")
text = text.replace("DEVICE_DESC_PARAM_FEAT_SUP", "DEVICE_DESC_PARAM_UFS_FEAT")
start = text.index("static ssize_t dump_string_desc_serial_show(")
end = text.index("static DEVICE_ATTR_RO(dump_string_desc_serial);", start)
serial_fn = """static ssize_t dump_string_desc_serial_show(struct device *dev,
    struct device_attribute *attr, char *buf)
{
    u8 ser_number[128] = { 0 };
    int i = 0, count = 0;
    struct ufs_hba *hba = get_ufs_hba_data();

    ufs_get_string_desc(hba, &ser_number, sizeof(ser_number),
                        DEVICE_DESC_PARAM_SN, SD_RAW);

    count += snprintf((buf + count), PAGE_SIZE, "serial:");

    for (i = 2; i < ser_number[QUERY_DESC_LENGTH_OFFSET]; i += 2)
        count += snprintf((buf + count), PAGE_SIZE, "%02x%02x",
                          ser_number[i], ser_number[i + 1]);

    count += snprintf((buf + count), PAGE_SIZE, "\\n");

    return count;
}
"""
text = text[:start] + serial_fn + text[end:]
path.write_text(text)

# Linux 5.4.289 proc_create() expects struct proc_ops.
path = Path("drivers/misc/mi-memory/mv.c")
text = path.read_text()
old = """static const struct file_operations mv_proc_fops = {
	.open		= mv_proc_open,
	.read		= seq_read,
	.llseek		= seq_lseek,
	.release	= single_release,
};"""
new = """static const struct proc_ops mv_proc_fops = {
	.proc_open	= mv_proc_open,
	.proc_read	= seq_read,
	.proc_lseek	= seq_lseek,
	.proc_release	= single_release,
};"""
if old not in text:
    raise SystemExit("mi-memory mv procfs file_operations block not found")
text = text.replace(old, new, 1)
path.write_text(text)
PY

# Stock HyperOS has mi_memory.ko importing get_ufs_* symbols from vmlinux.
# Keep mem_interface built-in while mi_memory remains a module.
cat > drivers/misc/mi-memory/Makefile <<'EOF'
# SPDX-License-Identifier: GPL-2.0
obj-$(CONFIG_MI_MEMORY_SYSFS) += mi_memory.o
mi_memory-y += mi_memory_sysfs.o
mi_memory-y += mi_ufs_info.o
mi_memory-y += mi_dram_info.o
mi_memory-y += mv.o
mi_memory-y += mi_mem_type.o
obj-y += mem_interface.o
EOF

grep -q 'source "drivers/misc/mi-memory/Kconfig"' drivers/misc/Kconfig ||     sed -i '/endmenu/i source "drivers/misc/mi-memory/Kconfig"' drivers/misc/Kconfig

# Always descend into mi-memory so mem_interface.o can be built into vmlinux
# even when CONFIG_MI_MEMORY_SYSFS=m. This matches Xiaomi's source layout where
# mi_memory.ko is modular but mem_interface.o is built-in.
sed -i '/CONFIG_MI_MEMORY_SYSFS.*mi-memory\//d' drivers/misc/Makefile
grep -qE '^[[:space:]]*obj-y[[:space:]]*\+=[[:space:]]*mi-memory/' drivers/misc/Makefile || \
    printf '\nobj-y += mi-memory/\n' >> drivers/misc/Makefile
echo "::endgroup::"

echo "::group::Wire Xiaomi mi-memory into UFS core"
python3 - <<'PY'
from pathlib import Path

path = Path("drivers/scsi/ufs/ufshcd.c")
text = path.read_text()

decl = """#ifdef CONFIG_MI_MEMORY_SYSFS
extern void set_ufs_hba_data(struct scsi_device *sdev);
#endif

"""
needle = "/**\n * ufshcd_slave_configure - adjust SCSI device configurations"
if "extern void set_ufs_hba_data" not in text:
    if needle not in text:
        raise SystemExit("ufshcd_slave_configure declaration point not found")
    text = text.replace(needle, decl + needle, 1)

hook = """#ifdef CONFIG_MI_MEMORY_SYSFS
	if (sdev->lun == 0)
		set_ufs_hba_data(sdev);
#endif

"""
ret_needle = """	if (ufshcd_is_rpm_autosuspend_allowed(hba))
		sdev->rpm_autosuspend = 1;

	return 0;
}"""
if "set_ufs_hba_data(sdev);" not in text:
    if ret_needle not in text:
        raise SystemExit("ufshcd_slave_configure body point not found")
    text = text.replace(
        ret_needle,
        """	if (ufshcd_is_rpm_autosuspend_allowed(hba))
		sdev->rpm_autosuspend = 1;

""" + hook + """	return 0;
}""",
        1,
    )

path.write_text(text)
PY
echo "::endgroup::"

echo "::group::Import Xiaomi CNSS statistics"
git clone --depth=1 --branch "$MI_CNSS_REF" "$MI_CNSS_REPO" "$WORK_ROOT/mi-cnss"
rm -rf drivers/net/wireless/mi_cnss_statistic
cp -a "$WORK_ROOT/mi-cnss/drivers/net/wireless/mi_cnss_statistic" drivers/net/wireless/mi_cnss_statistic

grep -q 'mi_cnss_statistic/' drivers/net/wireless/Makefile ||     printf '\nobj-$(CONFIG_MI_CNSS_STATISTIC) += mi_cnss_statistic/\n' >> drivers/net/wireless/Makefile

grep -q 'source "drivers/net/wireless/mi_cnss_statistic/Kconfig"' drivers/net/wireless/Kconfig ||     sed -i '/endif # WLAN/i source "drivers/net/wireless/mi_cnss_statistic/Kconfig"' drivers/net/wireless/Kconfig
echo "::endgroup::"

echo "::group::Target config"
CFG=arch/arm64/configs/vendor/lisa_QGKI.config
test -f "$CFG"

set_cfg() {
    local key="$1"
    local line="$2"
    sed -i "/^${key}=.*/d;/^# ${key} is not set$/d" "$CFG"
    printf '%s\n' "$line" >> "$CFG"
}

set_cfg CONFIG_LOCALVERSION 'CONFIG_LOCALVERSION="-qgki"'
set_cfg CONFIG_LOCALVERSION_AUTO 'CONFIG_LOCALVERSION_AUTO=y'
set_cfg CONFIG_MI_MEMORY_SYSFS 'CONFIG_MI_MEMORY_SYSFS=m'
set_cfg CONFIG_MI_CNSS_STATISTIC 'CONFIG_MI_CNSS_STATISTIC=m'
set_cfg CONFIG_MI_HARDWARE_ID 'CONFIG_MI_HARDWARE_ID=m'
set_cfg CONFIG_MI_THERMAL_INTERFACE 'CONFIG_MI_THERMAL_INTERFACE=m'
set_cfg CONFIG_USB_F_DTP 'CONFIG_USB_F_DTP=m'
set_cfg CONFIG_QGKI_SYSTEM 'CONFIG_QGKI_SYSTEM=y'
set_cfg CONFIG_ARCH_YUPIK 'CONFIG_ARCH_YUPIK=y'
set_cfg CONFIG_PINCTRL_SM7325 'CONFIG_PINCTRL_SM7325=y'

# Preserve stock CONFIG_LOCALVERSION_AUTO=y semantics while forcing the
# shipping SCM suffix instead of the reconstruction repository commit hash.
printf -- '-%s\n' "$TARGET_GIT_SUFFIX" > .scmversion
echo "::endgroup::"

echo "::group::Copy reconstruction provenance"
mkdir -p reconstruction scripts
cp "$META_ROOT/reconstruction/manifest.env" reconstruction/manifest.env
cp "$META_ROOT/scripts/check_reconstruction.sh" scripts/check_reconstruction.sh
chmod +x scripts/check_reconstruction.sh

cat > reconstruction/STATUS.md <<EOF
# Xiaomi lisa HyperOS kernel reconstruction

Target binary:
- ROM: \`$TARGET_ROM\`
- Kernel: \`$TARGET_VERMAGIC\`
- Device: \`$TARGET_DEVICE\`
- SoC: \`$TARGET_SOC / $TARGET_PLATFORM\`

Source construction:
- MIUI device baseline: \`$BASE_REPO @ $BASE_REF\`
- Android/Qualcomm 5.4.289 merge: \`$STABLE_REPO @ $STABLE_COMMIT\`
- Xiaomi mi-memory donor: \`$MI_MEMORY_REPO @ $MI_MEMORY_REF\`
- Xiaomi CNSS statistics donor: \`$MI_CNSS_REPO @ $MI_CNSS_REF\`
- Historical device reference: \`$MICODE_REPO @ $MICODE_REF\`

## Validation state

This branch is a **reconstruction candidate**, not yet a claimed stock-equivalent kernel.

Required before stock-equivalent status:
1. Build with the stock-compatible clang/QGKI configuration.
2. Compare \`Module.symvers\` CRCs with HyperOS stock modules.
3. Validate all stock QGKI vendor modules load without unknown-symbol/version failures.
4. Validate DTB/DTBO/vendor_boot compatibility.
5. Boot-test on lisa and inspect early boot/module logs.
6. Only after the stock-compatible baseline works, extend BPF/BTF features.
EOF
echo "::endgroup::"

"$META_ROOT/scripts/check_reconstruction.sh" || exit 40

git add -A
# .scmversion is ignored by the kernel tree by design, but this reconstruction
# must carry the shipping SCM suffix into a fresh Git checkout.
git add -f .scmversion
git commit -m "lisa: reconstruct HyperOS 5.4.289 QGKI baseline"

echo "Prepared source tree: $SRC"
