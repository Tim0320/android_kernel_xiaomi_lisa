# Candidate0061 diagnostic boot: log-first engineering gate (2026-10-12)

Status: SPECIFICATION_ONLY / NOT_BUILT / NOT_FLASH_AUTHORIZED
Baseline: HyperOS 3.0.9 Android 16; direct Linux 5.4.302 SM7325/Yupik.
Policy: LOCAL_BUILD_PRIMARY + CI_AUDIT_ONLY. Do not modify C0059 frozen r43da7c5, vendor EROFS, vbmeta, AVB, SELinux or thermal. No A17/BPF.
Existing immutable integrated run: 38112707005 artifact 11693027992, source r16348a6. A fresh diagnostic boot requires a NEW kernel build if config or kernel logging code is changed. Packaging the unchanged Image only cannot add tracing.

## Primary goal
Preserve the *first actual fault* in Android startup and distinguish: initial QGKI modprobe probe -> potential whole-directory GKI fallback -> later module failures -> NFC cdev panic/reboot. The OEM vendor_modprobe.sh is the decision maker, not modules.load first line. This is a hypothesis: actual first probe and runtime branch UNKNOWN.

## Before a new diagnostic compile
1. Read true built .config and target hardware DT / bootargs; check CONFIG_PSTORE, CONFIG_PSTORE_RAM, CONFIG_RAMOOPS, CONFIG_PRINTK, CONFIG_PRINTK_TIME, CONFIG_KALLSYMS, CONFIG_MAGIC_SYSRQ, CONFIG_PANIC_ON_OOPS, CONFIG_PANIC_TIMEOUT and effective pstore/ramoops reserved-memory availability. Absence of an existing reserved memory region means enabling CONFIG_PSTORE_RAM alone is insufficient. Never invent ramoops addresses or reuse occupied memory.
2. Confirm existing on-device persistence: previous recovery captures reported empty /sys/fs/pstore, but some prior real Lisa captures had separate partition OEM Oops. Distinguish stale entries by boot ID, timestamps, SHA, and unique event marker; never count old logs as new.
3. Prefer existing OEM reserved logger / pstore / ramoops without altering DT or partitions. If no validated persistent sink, label POST_REBOOT_CAPTURE_NOT_PROVEN. Kernel printk verbosity only increases messages; it does not guarantee persistence after reset.
4. Keep earlycon/console untouched unless serial transport, UART and pinmux are specifically verified. Avoid printk flood, log_buf excessive RAM, or panic policies that mask original reset.
5. Verify init.target.rc early-init vendor_modprobe.sh, early-fs cnss2/icnss2 and boot WLAN async calls. There is NO demonstrated real Android first-probe order: vendor modprobe -l and missing blocklist/aliases must be read back rather than inferred from modules.load order.
6. Full same-build static/ABI/KMI/identity/repack verification, dual-slot rollback mapping and boot partition geometry; no artifact labeled flashable until all independent gate results and recovery plan are documented.

## Diagnostic output contract
- diagnostic-build-manifest.json: commit SHA, exact config hash, Image SHA, boot SHA, vendor_boot hash (unchanged or explicitly checked), Module.symvers SHA, compiler identity, selected instrumentation and risks.
- diagnostic-pstore-capability.json: CONFIG_* effective values, DT reserved-memory provenance, pstore backend availability, proposed capture path and limitations.
- diagnostic-loader-route.json: known static branch semantics vs UNKNOWN runtime path and first probe, expected modprobe stderr/kernel signatures, NFC QGKI 71/71 CRC and GKI 32/68 warning.
- release-gate.json must default to NOT_FLASHABLE and include reason list; if logs will not survive restart, say so.
- On a future user-authorized device test, recovery read-only capture must include fresh /sys/fs/pstore, OEM Oops area where supported, partition/kernel identity, and timestamps. Do NOT read Recovery uname/dmesg as if Android kernel ran.

## Present status
Boot already exists from previous CI, but NO diagnostic rebuild, NO fresh boot artifact, NO new device runtime, and NO permission to flash from this note. This note is not evidence that the diagnostic sink works.
