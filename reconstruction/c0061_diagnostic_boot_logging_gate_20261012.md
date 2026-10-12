# Candidate0061 diagnostic boot: log-first engineering gate (2026-10-12)

Status: SPECIFICATION_ONLY / NOT_BUILT / NOT_FLASH_AUTHORIZED
Baseline: HyperOS 3.0.9 Android 16; direct Linux 5.4.302 SM7325/Yupik.
Policy: LOCAL_BUILD_PRIMARY + CI_AUDIT_ONLY. Do not modify C0059 frozen r43da7c5, vendor EROFS, vbmeta, AVB, SELinux or thermal. No A17/BPF.
Existing immutable integrated run: 38112707005 artifact 11693027992, source r16348a6. A fresh diagnostic boot requires a NEW kernel build if config or kernel logging code is changed. Packaging the unchanged Image only cannot add tracing.

## Primary goal
Prioritize the ALREADY CAPTURED OEM persistent memory/partition Oops and established Android NFC first fault, then distinguish QGKI/GKI module origin and additional earlier loader errors. The documented C0061 boot-relative ~41.7s nqnfcinfo -> nfc_dev_open -> mutex_lock Oops and fatal panic in a real 16MiB OEM `oops` partition is stronger causal evidence than first-probe speculation. First QGKI probe and runtime GKI fallback remain UNKNOWN. Do not substitute pstore emptiness for Android stage evidence.

## Before a new diagnostic compile
0. Before building anything, reuse the verified original OEM mtdoops evidence (reconstruction/c0061_twrp_new_nfc_panic_20261010_2245.md): Oops partition SHA256 0e034b59946d562344dfb0295ce3cd0e6141f31bf4b685829ff2224f5b277e47; Android Kernel 5.4.302 C0061 NFC panic at ~41-44 seconds, loaded nfc_i2c, nqnfcinfo process. Verify this OEM storage path and consumer tool; do not design a duplicate pstore backend or claim it is missing. A fresh boot's record must be distinguished from ring-buffer retained older crashes by kernel identity, timestamps, hash and event content.
1. Read true built .config and target hardware DT / bootargs; check CONFIG_PSTORE, CONFIG_PSTORE_RAM, CONFIG_RAMOOPS, CONFIG_PRINTK, CONFIG_PRINTK_TIME, CONFIG_KALLSYMS, CONFIG_MAGIC_SYSRQ, CONFIG_PANIC_ON_OOPS, CONFIG_PANIC_TIMEOUT and effective pstore/ramoops reserved-memory availability. Absence of an existing reserved memory region means enabling CONFIG_PSTORE_RAM alone is insufficient. Never invent ramoops addresses or reuse occupied memory.
2. Confirm existing on-device persistence: previous recovery captures reported empty /sys/fs/pstore, but some prior real Lisa captures had separate partition OEM Oops. Distinguish stale entries by boot ID, timestamps, SHA, and unique event marker; never count old logs as new.
3. Prefer existing OEM Oops persistent partition/logger FIRST. Treat pstore as optional auxiliary capture, not prerequisite; absence of pstore data is not evidence that no system userspace ran (already captured nqnfcinfo panic at ~41s with empty recovery pstore). If no validated persistent sink, label POST_REBOOT_CAPTURE_NOT_PROVEN. Kernel printk verbosity only increases messages; it does not guarantee persistence after reset.
4. Keep earlycon/console untouched unless serial transport, UART and pinmux are specifically verified. Avoid printk flood, log_buf excessive RAM, or panic policies that mask original reset.
5. Verify init.target.rc early-init vendor_modprobe.sh, early-fs cnss2/icnss2 and boot WLAN async calls. There is NO demonstrated real Android first-probe order: vendor modprobe -l and missing blocklist/aliases must be read back rather than inferred from modules.load order.
6. Full same-build static/ABI/KMI/identity/repack verification, dual-slot rollback mapping and boot partition geometry; no artifact labeled flashable until all independent gate results and recovery plan are documented.

## Existing proven first fault and remediation constraint
- nqnfcinfo calling NFC char device triggered invalid-pointer Oops at nfc_dev_open -> mutex_lock and kernel panic, confirmed by previously captured OEM oops bytes. QGKI vs GKI origin of the loaded nfc_i2c is still unproven.
- Guarded NFC module was built separately but NOT deployed in OEM EROFS vendor. Repacking/reflashing identical boot Image cannot supply this guard. Avoid rebuilding diagnostic-only kernel before considering the proven NFC fault and a safe, compatible paired deployment strategy.
- Any new markers must reach the existing verified OEM logger path; adding printk text alone does not establish it reaches persistent storage.

## Diagnostic output contract
- diagnostic-build-manifest.json: commit SHA, exact config hash, Image SHA, boot SHA, vendor_boot hash (unchanged or explicitly checked), Module.symvers SHA, compiler identity, selected instrumentation and risks.
- diagnostic-pstore-capability.json: CONFIG_* effective values, DT reserved-memory provenance, pstore backend availability, proposed capture path and limitations.
- diagnostic-loader-route.json: known static branch semantics vs UNKNOWN runtime path and first probe, expected modprobe stderr/kernel signatures, NFC QGKI 71/71 CRC and GKI 32/68 warning.
- release-gate.json must default to NOT_FLASHABLE and include reason list; if logs will not survive restart, say so.
- On a future user-authorized device test, recovery read-only capture must include fresh /sys/fs/pstore, OEM Oops area where supported, partition/kernel identity, and timestamps. Do NOT read Recovery uname/dmesg as if Android kernel ran.

## Present status
Boot already exists from previous CI, but NO diagnostic rebuild, NO fresh boot artifact, NO new device runtime, and NO permission to flash from this note. This note is not evidence that the diagnostic sink works.
