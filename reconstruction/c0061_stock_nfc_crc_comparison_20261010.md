# Candidate0061 5.4.302 versus authentic stock Lisa NFC modules — CRC results

Date: 2026-10-10, Asia/Taipei. **OFFLINE ELF + SYMBOL CRC EVIDENCE, NOT A DEVICE BOOT TEST.**

## Provenance

- User uploaded `lisa_nfc_crc_20261010-215518.zip`, verified ZIP SHA256 `c7beb4f6de91e6952bd41b2b191be5748f92f3ab8f4e37a5710f9a0dec730a71`, containing two ELF64 little-endian AArch64 modules, each matching the earlier TWRP v1.4.0 read-only vendor_a EROFS hashes:
  - `qgki_nfc_i2c.ko` from `/vendor/lib/modules/nfc_i2c.ko`, 62704 bytes, SHA256 `b37dae41aad83b6adaa1f2a16253d2a8ca931b83a534fd5fb57ceaea2424bc68`, vermagic `5.4.289-qgki-g5987d69e25da SMP preempt mod_unload modversions aarch64`.
  - `gki_nfc_i2c.ko` from `/vendor/lib/modules/5.4-gki/nfc_i2c.ko`, 61768 bytes, SHA256 `bb1e8994d0ddf0b15bd038457a850b2a8b5c7b74e1816b97dea5623c2ea5c80b`, vermagic `5.4.289-g5987d69e25da SMP preempt mod_unload modversions aarch64`.
- Reference **actual** C0061 Direct-302 integrated build `kernel/out/Module.symvers`: Action [`38056564905`](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38056564905), artifact `11672061727`, 830233-byte `Module.symvers`, tied to real kernel build `37655937871` and kernelrelease `5.4.302-qgki-lisa-c0061-rfb3b3c2-by-Tim0320`.
- Extraction: `llvm-objcopy --dump-section __versions` on **disposable offline temporary copies**, 64-byte ARM64 `modversion_info` entries `<Q56s`, no writing to phone partitions. Both `module_layout` anchors present; exported `Module.symvers` values decoded as 32-bit CRCs. Exact raw OEM binaries **have not been uploaded to public GitHub**.

## Quantified result

| Original vendor NFC file | Imported CRCs | Exact matches vs C0061 | Missing symbols | CRC mismatches | module_layout CRC | Static interpretation |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| QGKI (vendor/lib/modules/nfc_i2c.ko) | **71** | **71/71** | **0** | **0** | `0xba39cbb8` = `0xba39cbb8` | All imported CRCs match candidate |
| GKI (vendor/lib/modules/5.4-gki/nfc_i2c.ko) | **68** | **36/68** | **0** | **32** | `0x1e5b7ab7` != `0xba39cbb8` | High-confidence *symbol-version ABI mismatch* if this variant is loaded into C0061 with normal MODVERSIONS |

The two stock NFC variants share 68 imported symbol names; the QGKI variant imports three additional symbols. All 32 GKI CRC differences are also different from the QGKI CRCs for the corresponding symbol names. Affected symbols include `module_layout`, `cdev_init/cdev_add/cdev_del`, `__class_create`, `device_create`, `i2c_register_driver`, `i2c_del_driver`, `gpio_to_desc`, `gpiod_direction_*`, `regulator_get/enable/disable` and memory allocation helpers. **No missing exported symbol names** in either candidate.

Crucially, a mere `5.4.289`/ `5.4.302` release string difference is not proof of rejection. Kernel code `same_magic` skips release-token comparison for CRC-equipped modules if CONFIG_MODVERSIONS is effective; the trailing flags are the same here. In contrast, the *actual* GKI symbol CRC mismatches, especially `module_layout`, are grounded incompatibility evidence. This static test does **not** prove the actual device accepted QGKI NFC (e.g. signature, namespaces, symbols in loaded dependencies, and runtime faults are not checked).

Sources for mechanism, not phone-observed load:
- Linux version logic and `same_magic`: https://kernel.googlesource.com/pub/scm/linux/kernel/git/stable/linux-stable/+/refs/tags/v5.15.62/kernel/module.c
- Android kernel module loading: https://source.android.com/docs/core/architecture/kernel/loadable-kernel-modules

## Triage implications and no-blind-flash rule

1. **Reduce blame on QGKI NFC version-only mismatch.** Its 71 imported CRCs match target 5.4.302. This does not prove it is loaded, functional, or carries the guarded NFC cdev fix; the guarded C0061 `nfc_i2c.ko` remains absent from inspected vendor files.
2. **Elevate whole-directory GKI fallback branch as a conditional risk.** Proprietary `vendor_modprobe.sh` chooses GKI for all remaining module attempts **only if the first QGKI non-blocklisted module probe returns failure**. A later individual NFC failure does not cause per-module fallback. The actual first probe, selected branch, module load results and first contemporary reboot fault are not captured.
3. **Do not treat GKI CRC mismatch as a proven reboot root cause.** Even if the module is rejected, Android might continue; must correlate the actual first failed module and runtime crash. Assess whole 107-versus-227 module sets before any intervention.
4. **Next autonomous work:** verify installer/init/loader first probe and modprobe enumeration from existing source evidence; inspect C0061 QGKI kernel ABI stability and potential ways to record early module load errors; if no actionable software-only step remains, request a single targeted live Android ADB/persistent log that can distinguish QGKI vs GKI path. No repeat historical Oops/Logdump.
5. **Do not flash** the inspection-only NFC artifact or mutate EROFS/AVB / disable security. No new kernel source fix or `boot.img` exists as of this report.

Reproducible offline checker source (accepts private local ELF paths, commits no binaries): `reconstruction/scripts/candidate_0061_stock_nfc_crc_compare.py` (commit `aaab25f`). Its checker must not be represented as a physical Android boot test.

**Status:** `QGKI_STOCK_NFC_IMPORTED_CRC_PASS`; `GKI_STOCK_NFC_IMPORTED_CRC_32_MISMATCH`; `ANDROID_SELECTED_BRANCH_UNVERIFIED`; `CURRENT_BOOT_FIRST_FAULT_UNVERIFIED`.
