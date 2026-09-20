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

# Use a second Xiaomi 5.4 donor for the ABI-sensitive interface.
# This source family already matches the observed stock symbol names and
# signatures more closely: u8 memblock_mem_size_in_gb(), ufshcd_read_desc(),
# and hba-explicit UFS helper signatures.
git clone --no-checkout --filter=blob:none "$MI_MEMORY_ABI_REPO" "$WORK_ROOT/mi-memory-abi"
git -C "$WORK_ROOT/mi-memory-abi" fetch --depth=1 origin "$MI_MEMORY_ABI_COMMIT"
git -C "$WORK_ROOT/mi-memory-abi" checkout --detach FETCH_HEAD
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.c" drivers/misc/mi-memory/mem_interface.c
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.h" drivers/misc/mi-memory/mem_interface.h

# Keep the complete donor's users in sync with the integer ABI.
python3 - <<'PY'
from pathlib import Path
path = Path("drivers/misc/mi-memory/mi_dram_info.c")
text = path.read_text()
text = text.replace("double ddr_size_in_GB = 0;", "u8 ddr_size_in_GB = 0;")
text = text.replace('pr_err("memblock_mem_size %f\\n", ddr_size_in_GB);',
                    'pr_err("memblock_mem_size %d\\n", ddr_size_in_GB);')
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
set_cfg CONFIG_MI_MEMORY_SYSFS 'CONFIG_MI_MEMORY_SYSFS=m'
set_cfg CONFIG_MI_CNSS_STATISTIC 'CONFIG_MI_CNSS_STATISTIC=m'
set_cfg CONFIG_ARCH_YUPIK 'CONFIG_ARCH_YUPIK=y'
set_cfg CONFIG_PINCTRL_SM7325 'CONFIG_PINCTRL_SM7325=y'
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
git commit -m "lisa: reconstruct HyperOS 5.4.289 QGKI baseline"

echo "Prepared source tree: $SRC"
 Makefile ||    ! grep -q '^PATCHLEVEL = 4$' Makefile ||    ! grep -q '^SUBLEVEL = 289$' Makefile; then
    echo "Expected Linux 5.4.289 after stable merge." >&2
    head -n 8 Makefile >&2
    exit 31
fi

echo "::group::Import Xiaomi mi-memory"
git clone --depth=1 --branch "$MI_MEMORY_REF" "$MI_MEMORY_REPO" "$WORK_ROOT/mi-memory"
rm -rf drivers/misc/mi-memory
cp -a "$WORK_ROOT/mi-memory/drivers/misc/mi-memory" drivers/misc/mi-memory

# Use a second Xiaomi 5.4 donor for the ABI-sensitive interface.
# This source family already matches the observed stock symbol names and
# signatures more closely: u8 memblock_mem_size_in_gb(), ufshcd_read_desc(),
# and hba-explicit UFS helper signatures.
git clone --no-checkout --filter=blob:none "$MI_MEMORY_ABI_REPO" "$WORK_ROOT/mi-memory-abi"
git -C "$WORK_ROOT/mi-memory-abi" fetch --depth=1 origin "$MI_MEMORY_ABI_COMMIT"
git -C "$WORK_ROOT/mi-memory-abi" checkout --detach FETCH_HEAD
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.c" drivers/misc/mi-memory/mem_interface.c
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.h" drivers/misc/mi-memory/mem_interface.h

# Keep the complete donor's users in sync with the integer ABI.
python3 - <<'PY'
from pathlib import Path
path = Path("drivers/misc/mi-memory/mi_dram_info.c")
text = path.read_text()
text = text.replace("double ddr_size_in_GB = 0;", "u8 ddr_size_in_GB = 0;")
text = text.replace('pr_err("memblock_mem_size %f\\n", ddr_size_in_GB);',
                    'pr_err("memblock_mem_size %d\\n", ddr_size_in_GB);')
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
set_cfg CONFIG_MI_MEMORY_SYSFS 'CONFIG_MI_MEMORY_SYSFS=m'
set_cfg CONFIG_MI_CNSS_STATISTIC 'CONFIG_MI_CNSS_STATISTIC=m'
set_cfg CONFIG_ARCH_YUPIK 'CONFIG_ARCH_YUPIK=y'
set_cfg CONFIG_PINCTRL_SM7325 'CONFIG_PINCTRL_SM7325=y'
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
git commit -m "lisa: reconstruct HyperOS 5.4.289 QGKI baseline"

echo "Prepared source tree: $SRC"
 Makefile || \
   ! grep -q '^PATCHLEVEL = 4
    echo "Expected Linux 5.4.289 after stable merge." >&2
    head -n 8 Makefile >&2
    exit 31
fi

echo "::group::Import Xiaomi mi-memory"
git clone --depth=1 --branch "$MI_MEMORY_REF" "$MI_MEMORY_REPO" "$WORK_ROOT/mi-memory"
rm -rf drivers/misc/mi-memory
cp -a "$WORK_ROOT/mi-memory/drivers/misc/mi-memory" drivers/misc/mi-memory

# Use a second Xiaomi 5.4 donor for the ABI-sensitive interface.
# This source family already matches the observed stock symbol names and
# signatures more closely: u8 memblock_mem_size_in_gb(), ufshcd_read_desc(),
# and hba-explicit UFS helper signatures.
git clone --no-checkout --filter=blob:none "$MI_MEMORY_ABI_REPO" "$WORK_ROOT/mi-memory-abi"
git -C "$WORK_ROOT/mi-memory-abi" fetch --depth=1 origin "$MI_MEMORY_ABI_COMMIT"
git -C "$WORK_ROOT/mi-memory-abi" checkout --detach FETCH_HEAD
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.c" drivers/misc/mi-memory/mem_interface.c
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.h" drivers/misc/mi-memory/mem_interface.h

# Keep the complete donor's users in sync with the integer ABI.
python3 - <<'PY'
from pathlib import Path
path = Path("drivers/misc/mi-memory/mi_dram_info.c")
text = path.read_text()
text = text.replace("double ddr_size_in_GB = 0;", "u8 ddr_size_in_GB = 0;")
text = text.replace('pr_err("memblock_mem_size %f\\n", ddr_size_in_GB);',
                    'pr_err("memblock_mem_size %d\\n", ddr_size_in_GB);')
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
set_cfg CONFIG_MI_MEMORY_SYSFS 'CONFIG_MI_MEMORY_SYSFS=m'
set_cfg CONFIG_MI_CNSS_STATISTIC 'CONFIG_MI_CNSS_STATISTIC=m'
set_cfg CONFIG_ARCH_YUPIK 'CONFIG_ARCH_YUPIK=y'
set_cfg CONFIG_PINCTRL_SM7325 'CONFIG_PINCTRL_SM7325=y'
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
git commit -m "lisa: reconstruct HyperOS 5.4.289 QGKI baseline"

echo "Prepared source tree: $SRC"
 Makefile ||    ! grep -q '^PATCHLEVEL = 4$' Makefile ||    ! grep -q '^SUBLEVEL = 289$' Makefile; then
    echo "Expected Linux 5.4.289 after stable merge." >&2
    head -n 8 Makefile >&2
    exit 31
fi

echo "::group::Import Xiaomi mi-memory"
git clone --depth=1 --branch "$MI_MEMORY_REF" "$MI_MEMORY_REPO" "$WORK_ROOT/mi-memory"
rm -rf drivers/misc/mi-memory
cp -a "$WORK_ROOT/mi-memory/drivers/misc/mi-memory" drivers/misc/mi-memory

# Use a second Xiaomi 5.4 donor for the ABI-sensitive interface.
# This source family already matches the observed stock symbol names and
# signatures more closely: u8 memblock_mem_size_in_gb(), ufshcd_read_desc(),
# and hba-explicit UFS helper signatures.
git clone --no-checkout --filter=blob:none "$MI_MEMORY_ABI_REPO" "$WORK_ROOT/mi-memory-abi"
git -C "$WORK_ROOT/mi-memory-abi" fetch --depth=1 origin "$MI_MEMORY_ABI_COMMIT"
git -C "$WORK_ROOT/mi-memory-abi" checkout --detach FETCH_HEAD
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.c" drivers/misc/mi-memory/mem_interface.c
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.h" drivers/misc/mi-memory/mem_interface.h

# Keep the complete donor's users in sync with the integer ABI.
python3 - <<'PY'
from pathlib import Path
path = Path("drivers/misc/mi-memory/mi_dram_info.c")
text = path.read_text()
text = text.replace("double ddr_size_in_GB = 0;", "u8 ddr_size_in_GB = 0;")
text = text.replace('pr_err("memblock_mem_size %f\\n", ddr_size_in_GB);',
                    'pr_err("memblock_mem_size %d\\n", ddr_size_in_GB);')
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
set_cfg CONFIG_MI_MEMORY_SYSFS 'CONFIG_MI_MEMORY_SYSFS=m'
set_cfg CONFIG_MI_CNSS_STATISTIC 'CONFIG_MI_CNSS_STATISTIC=m'
set_cfg CONFIG_ARCH_YUPIK 'CONFIG_ARCH_YUPIK=y'
set_cfg CONFIG_PINCTRL_SM7325 'CONFIG_PINCTRL_SM7325=y'
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
git commit -m "lisa: reconstruct HyperOS 5.4.289 QGKI baseline"

echo "Prepared source tree: $SRC"
 Makefile || \
   ! grep -q '^SUBLEVEL = 289
    echo "Expected Linux 5.4.289 after stable merge." >&2
    head -n 8 Makefile >&2
    exit 31
fi

echo "::group::Import Xiaomi mi-memory"
git clone --depth=1 --branch "$MI_MEMORY_REF" "$MI_MEMORY_REPO" "$WORK_ROOT/mi-memory"
rm -rf drivers/misc/mi-memory
cp -a "$WORK_ROOT/mi-memory/drivers/misc/mi-memory" drivers/misc/mi-memory

# Use a second Xiaomi 5.4 donor for the ABI-sensitive interface.
# This source family already matches the observed stock symbol names and
# signatures more closely: u8 memblock_mem_size_in_gb(), ufshcd_read_desc(),
# and hba-explicit UFS helper signatures.
git clone --no-checkout --filter=blob:none "$MI_MEMORY_ABI_REPO" "$WORK_ROOT/mi-memory-abi"
git -C "$WORK_ROOT/mi-memory-abi" fetch --depth=1 origin "$MI_MEMORY_ABI_COMMIT"
git -C "$WORK_ROOT/mi-memory-abi" checkout --detach FETCH_HEAD
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.c" drivers/misc/mi-memory/mem_interface.c
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.h" drivers/misc/mi-memory/mem_interface.h

# Keep the complete donor's users in sync with the integer ABI.
python3 - <<'PY'
from pathlib import Path
path = Path("drivers/misc/mi-memory/mi_dram_info.c")
text = path.read_text()
text = text.replace("double ddr_size_in_GB = 0;", "u8 ddr_size_in_GB = 0;")
text = text.replace('pr_err("memblock_mem_size %f\\n", ddr_size_in_GB);',
                    'pr_err("memblock_mem_size %d\\n", ddr_size_in_GB);')
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
set_cfg CONFIG_MI_MEMORY_SYSFS 'CONFIG_MI_MEMORY_SYSFS=m'
set_cfg CONFIG_MI_CNSS_STATISTIC 'CONFIG_MI_CNSS_STATISTIC=m'
set_cfg CONFIG_ARCH_YUPIK 'CONFIG_ARCH_YUPIK=y'
set_cfg CONFIG_PINCTRL_SM7325 'CONFIG_PINCTRL_SM7325=y'
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
git commit -m "lisa: reconstruct HyperOS 5.4.289 QGKI baseline"

echo "Prepared source tree: $SRC"
 Makefile ||    ! grep -q '^PATCHLEVEL = 4$' Makefile ||    ! grep -q '^SUBLEVEL = 289$' Makefile; then
    echo "Expected Linux 5.4.289 after stable merge." >&2
    head -n 8 Makefile >&2
    exit 31
fi

echo "::group::Import Xiaomi mi-memory"
git clone --depth=1 --branch "$MI_MEMORY_REF" "$MI_MEMORY_REPO" "$WORK_ROOT/mi-memory"
rm -rf drivers/misc/mi-memory
cp -a "$WORK_ROOT/mi-memory/drivers/misc/mi-memory" drivers/misc/mi-memory

# Use a second Xiaomi 5.4 donor for the ABI-sensitive interface.
# This source family already matches the observed stock symbol names and
# signatures more closely: u8 memblock_mem_size_in_gb(), ufshcd_read_desc(),
# and hba-explicit UFS helper signatures.
git clone --no-checkout --filter=blob:none "$MI_MEMORY_ABI_REPO" "$WORK_ROOT/mi-memory-abi"
git -C "$WORK_ROOT/mi-memory-abi" fetch --depth=1 origin "$MI_MEMORY_ABI_COMMIT"
git -C "$WORK_ROOT/mi-memory-abi" checkout --detach FETCH_HEAD
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.c" drivers/misc/mi-memory/mem_interface.c
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.h" drivers/misc/mi-memory/mem_interface.h

# Keep the complete donor's users in sync with the integer ABI.
python3 - <<'PY'
from pathlib import Path
path = Path("drivers/misc/mi-memory/mi_dram_info.c")
text = path.read_text()
text = text.replace("double ddr_size_in_GB = 0;", "u8 ddr_size_in_GB = 0;")
text = text.replace('pr_err("memblock_mem_size %f\\n", ddr_size_in_GB);',
                    'pr_err("memblock_mem_size %d\\n", ddr_size_in_GB);')
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
set_cfg CONFIG_MI_MEMORY_SYSFS 'CONFIG_MI_MEMORY_SYSFS=m'
set_cfg CONFIG_MI_CNSS_STATISTIC 'CONFIG_MI_CNSS_STATISTIC=m'
set_cfg CONFIG_ARCH_YUPIK 'CONFIG_ARCH_YUPIK=y'
set_cfg CONFIG_PINCTRL_SM7325 'CONFIG_PINCTRL_SM7325=y'
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
git commit -m "lisa: reconstruct HyperOS 5.4.289 QGKI baseline"

echo "Prepared source tree: $SRC"
 Makefile; then
    echo "Expected Linux 5.4.289 after stable merge." >&2
    head -n 8 Makefile >&2
    exit 31
fi

echo "::group::Import Xiaomi mi-memory"
git clone --depth=1 --branch "$MI_MEMORY_REF" "$MI_MEMORY_REPO" "$WORK_ROOT/mi-memory"
rm -rf drivers/misc/mi-memory
cp -a "$WORK_ROOT/mi-memory/drivers/misc/mi-memory" drivers/misc/mi-memory

# Use a second Xiaomi 5.4 donor for the ABI-sensitive interface.
# This source family already matches the observed stock symbol names and
# signatures more closely: u8 memblock_mem_size_in_gb(), ufshcd_read_desc(),
# and hba-explicit UFS helper signatures.
git clone --no-checkout --filter=blob:none "$MI_MEMORY_ABI_REPO" "$WORK_ROOT/mi-memory-abi"
git -C "$WORK_ROOT/mi-memory-abi" fetch --depth=1 origin "$MI_MEMORY_ABI_COMMIT"
git -C "$WORK_ROOT/mi-memory-abi" checkout --detach FETCH_HEAD
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.c" drivers/misc/mi-memory/mem_interface.c
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.h" drivers/misc/mi-memory/mem_interface.h

# Keep the complete donor's users in sync with the integer ABI.
python3 - <<'PY'
from pathlib import Path
path = Path("drivers/misc/mi-memory/mi_dram_info.c")
text = path.read_text()
text = text.replace("double ddr_size_in_GB = 0;", "u8 ddr_size_in_GB = 0;")
text = text.replace('pr_err("memblock_mem_size %f\\n", ddr_size_in_GB);',
                    'pr_err("memblock_mem_size %d\\n", ddr_size_in_GB);')
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
set_cfg CONFIG_MI_MEMORY_SYSFS 'CONFIG_MI_MEMORY_SYSFS=m'
set_cfg CONFIG_MI_CNSS_STATISTIC 'CONFIG_MI_CNSS_STATISTIC=m'
set_cfg CONFIG_ARCH_YUPIK 'CONFIG_ARCH_YUPIK=y'
set_cfg CONFIG_PINCTRL_SM7325 'CONFIG_PINCTRL_SM7325=y'
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
git commit -m "lisa: reconstruct HyperOS 5.4.289 QGKI baseline"

echo "Prepared source tree: $SRC"
 Makefile ||    ! grep -q '^PATCHLEVEL = 4$' Makefile ||    ! grep -q '^SUBLEVEL = 289$' Makefile; then
    echo "Expected Linux 5.4.289 after stable merge." >&2
    head -n 8 Makefile >&2
    exit 31
fi

echo "::group::Import Xiaomi mi-memory"
git clone --depth=1 --branch "$MI_MEMORY_REF" "$MI_MEMORY_REPO" "$WORK_ROOT/mi-memory"
rm -rf drivers/misc/mi-memory
cp -a "$WORK_ROOT/mi-memory/drivers/misc/mi-memory" drivers/misc/mi-memory

# Use a second Xiaomi 5.4 donor for the ABI-sensitive interface.
# This source family already matches the observed stock symbol names and
# signatures more closely: u8 memblock_mem_size_in_gb(), ufshcd_read_desc(),
# and hba-explicit UFS helper signatures.
git clone --no-checkout --filter=blob:none "$MI_MEMORY_ABI_REPO" "$WORK_ROOT/mi-memory-abi"
git -C "$WORK_ROOT/mi-memory-abi" fetch --depth=1 origin "$MI_MEMORY_ABI_COMMIT"
git -C "$WORK_ROOT/mi-memory-abi" checkout --detach FETCH_HEAD
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.c" drivers/misc/mi-memory/mem_interface.c
cp "$WORK_ROOT/mi-memory-abi/drivers/misc/mi-memory/mem_interface.h" drivers/misc/mi-memory/mem_interface.h

# Keep the complete donor's users in sync with the integer ABI.
python3 - <<'PY'
from pathlib import Path
path = Path("drivers/misc/mi-memory/mi_dram_info.c")
text = path.read_text()
text = text.replace("double ddr_size_in_GB = 0;", "u8 ddr_size_in_GB = 0;")
text = text.replace('pr_err("memblock_mem_size %f\\n", ddr_size_in_GB);',
                    'pr_err("memblock_mem_size %d\\n", ddr_size_in_GB);')
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
set_cfg CONFIG_MI_MEMORY_SYSFS 'CONFIG_MI_MEMORY_SYSFS=m'
set_cfg CONFIG_MI_CNSS_STATISTIC 'CONFIG_MI_CNSS_STATISTIC=m'
set_cfg CONFIG_ARCH_YUPIK 'CONFIG_ARCH_YUPIK=y'
set_cfg CONFIG_PINCTRL_SM7325 'CONFIG_PINCTRL_SM7325=y'
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
git commit -m "lisa: reconstruct HyperOS 5.4.289 QGKI baseline"

echo "Prepared source tree: $SRC"
