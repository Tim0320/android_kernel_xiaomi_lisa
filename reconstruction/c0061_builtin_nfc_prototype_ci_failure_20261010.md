# C0061 NFC=y built-in prototype — failed C0059-control gate, corrected and running

2026-10-10 Asia/Taipei. **Experimental; NOT FLASHABLE.**

## Exact first CI blocker and repair

Experimental Linux-stable Direct-302 prototype Action [38061878279](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38061878279) is **FAILED**, but it never reached the target Kernel Build. The actual failed step was `Prepare Candidate0059 same-run control config`. The known-good original control had `CONFIG_NFC_QTI_I2C=m` (NFC is a loadable module). A careless global workflow text edit added `grep -q '^CONFIG_NFC_QTI_I2C=y$'` to **both control and experimental target** sections; the frozen C0059 control was appropriately `=m` and the incorrect `=y` assertion failed. All previous source checkout, Direct-302 oracle downloads, frozen C0059 source generation, toolchain and stock-ABI preparation passed.

An attempted correction at `df878c8` accidentally corrupted YAML through text replacement. GitHub [38062918078](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38062918078) immediately **FAILED** at workflow parsing (zero build jobs). **Fixed** at commit [`f13410b`](https://github.com/Tim0320/android_kernel_xiaomi_lisa/commit/f13410bf8cbc8f7006ea8ff6206c6441babd4320) by restoring the entire last valid 624-line workflow from `a47b3b2` and modifying only two bounded sections: explicitly assert `CONFIG_NFC_QTI_I2C=m` in the *C0059 control*, and `CONFIG_NFC_QTI_I2C=y` plus `CONFIG_I2C=y` in the *C0061 target*. No change to frozen C0059 source. Source remains a clean isolated duplicate of the validated Direct-302 integrated workflow.

Re-triggered genuine build [`38062935154`](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38062935154): **IN_PROGRESS** at Direct-302 provenance fetch on latest query, and job is present. Do not call it a completed build/boot until actual Image, ABI, identity, fixed-region Boot packaging and artifacts all passed.

## Known runtime safety boundary — official source, not Lisa device proof

Source:
- Android libmodprobe `LoadWithAliases` maintains a loaded-module name cache, and may skip a module known already loaded: https://android.googlesource.com/platform/system/core/+/android16-qpr2-release/libmodprobe/libmodprobe.cpp
- Linux `finit_module` may return `EEXIST` when a module with the same name **is loaded**: https://man7.org/linux/man-pages/man2/init_module.2.html

**Crucial qualification**: A driver that is **built directly into `vmlinux`** is not necessarily the same state as an already-loaded `struct module` in the module loader's cache. The device proprietary `/vendor/bin/modprobe` is not byte-verified to Android upstream and still tries the stock QGKI/GKI `nfc_i2c.ko` from EROFS `/vendor/lib/modules`, so one cannot assume it avoids attempting a duplicate or that `EEXIST` fully resolves the conflict. An additional `nfc_i2c.ko` insertion might be rejected or might conflict during probe/driver or misc cdev registration. The prototype can validate compilation, not its Android runtime acceptance.

The TWRP 22:45 persistent C0061 fatal panic has actual `nqnfcinfo -> nfc_dev_open -> mutex_lock` fault, but guarded standalone .ko was never deployed; the `CONFIG_NFC_QTI_I2C=y` candidate is **new source/config behavior**, not a tested fix.

## Next engineering and reporting gates

1. Recheck Action `38062935154` job first failure, fix only grounded source/config blocker and rerun with a known-valid workflow. Track `last_checked_run=37655937871` as previous **completed** kernel reference until this one finishes.
2. If new `Image` and experimental `boot.img` are produced, validate all static/ABI/identity/packaging checks, `nfc_i2c.ko` absent from new build, cdev guard string present in `vmlinux`. Label artifact **NOT FLASHABLE** until old OEM module late-load, recovery rollback and packaging gates are closed.
3. Real Android ADB is unavailable. TWRP-only follow-up if strictly needed. Never ask to reflash identical Boot `038e35371c97...` or to install inspection-only NFC archive.
4. User fixed Windows log directory: `Set-Location "D:\1.ROM_Prot\lisa\pull_log"`. No new user data required at this stage.

Evidence classification: `PILOT_FIRST_FAILURE_C0059_CONTROL_ASSERTION_BUG`, `FIXED_VALID_WORKFLOW_RESTARTED`, `EXPERIMENTAL_BUILD_RUNNING`, `DEVICE_BOOT_PASS=NO`.
