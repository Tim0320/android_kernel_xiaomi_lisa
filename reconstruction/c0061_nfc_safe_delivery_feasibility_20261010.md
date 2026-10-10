# Candidate0061 NFC panic remediation — verified vendor_boot topology and guarded delivery decision

Date: 2026-10-10 (Asia/Taipei). **No new flashable image; static engineering feasibility and evidence only.**

## The proved failure requiring a functional change

The newly changed 22:45 TWRP oops from running C0061 5.4.302 contains boot-relative 41.8s `nqnfcinfo -> nfc_dev_open [nfc_i2c] -> mutex_lock` bad pointer `ffffffffffffffc8`, followed by Fatal exception / emergency_restart. `Modules linked in` **does contain NFC**, but the exact Android QGKI/GKI file that loaded is not proven. The new 5.4.302 **guarded NFC module already compiled**, SHA256 `aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b` and 71/71 imports match kernel symbols, is **absent from current EROFS vendor**. The boot image from run `37655937871` replaces Image only: reflashing unchanged boot `038e35371c97...` cannot deploy the guard.

Forensic source: `reconstruction/c0061_twrp_new_nfc_panic_20261010_2245.md`. Device cannot support actual Android ADB; only TWRP Recovery may supply additional physical readback.

## New CI readback: actual stock 3.0.9 vendor_boot ramdisk

Real Git LFS stock file: `reconstruction/stock/stock-Image-3.09/vendor_boot.img` SHA256 **`a94ecc2b8e53666693fd3cfc99ad07b5f24f586e85841728bf1d41333bc4b053`** (100663296 bytes, not yet the live phone's `vendor_boot_a` hash).

Read-only CI run [`38061521692`](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38061521692) **SUCCESS**, artifact [`11673670637`](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38061521692/artifacts/11673670637), downloaded and independently inspected `c0061-nfc-vendor-boot-placement.json`, `final-gate.txt`, `vendor-boot-layout.txt`.

- `VNDRBOOT` **header v3**, 4096-byte pages, one vendor ramdisk fragment (1,865,544 bytes), stock DTB 4,223,378 bytes.
- The actual unpacked ramdisk has **46** `.ko` binaries (distinct from 107 second-stage QGKI / 227 GKI vendor partition modules).
- Normal first-stage `modules.load` includes **only `msm_drm.ko`**, with normal first-stage QGKI ABI check PASS; the other **45** entries belong to alternate/recovery load listing and must not be mistaken for normal boot load.
- Neither a ramdisk binary named `nfc_i2c.ko` nor any `modules.load*` reference to NFC exists in this stock source snapshot. Guarded NFC SHA absent too.
- Therefore **copying the guarded `.ko` into vendor_boot alone would not make Android load it**. The already captured real device `vendor_modprobe.sh` explicitly looks under on-partition `/vendor/lib/modules` or `/vendor/lib/modules/5.4-gki`, neither of which is modified by a boot-only or plain vendor_boot placement change.
- This CI study is **repository stock vendor_boot**; **it does not prove the current device's vendor_boot partition is byte-identical**. Do not flash a modified vendor_boot without validating true device `vendor_boot_a` SHA and robust rollback.

Reusable offline proof gate `reconstruction/scripts/candidate_0061_vendor_boot_nfc_placement.py` commit `b1f9b00`, workflow integration `424f797` checks real Git LFS file and rejects pretending a stock ramdisk placement alone is a deployment.

## Candidate repair routes: no blind flash

**A. Guarded NFC preload from a reconstructed vendor_boot ramdisk** (possible, not implemented or runtime proven).
Android official first-stage init can load vendor ramdisk `/lib/modules/modules.load` in order; the stock image does not do so for NFC. A **real first-stage preload change** would need a correctly matched `.ko`, correctly rebuilt modules.dep/modules.load, proper first-stage ordering, actual `vendor_boot` identity / header / ramdisk compression, matching AVB and slot, and evidence that Android second-stage vendor modprobe treats already-loaded module as success. The vendor/proprietary binary's exact behavior and impact on recovery ramdisk must be checked. A second-stage load path is **not** redirected merely by a file in ramdisk. Bootloader orange reported in recovery alone does not authorize bypassing AVB or confirm an image safe to flash. **Current status: PRELOAD_SEQUENCE_AND_ROLLBACK_UNVERIFIED.**

**B. Build guarded QTI NFC directly into 5.4.302 Kernel Image** (potentially reversible through boot-only rollback, not built).
The authentic pre-uplift source `drivers/nfc/Kconfig` defines `CONFIG_NFC_QTI_I2C` as tristate, `depends on I2C`, and `drivers/nfc/qti/Makefile` compiles `nfc_i2c.o` from `nfc_common.o` + `nfc_i2c_drv.o` under that symbol. The verified C0061 build `.config` has **`CONFIG_NFC_QTI_I2C=m` and `CONFIG_I2C=y`**, with `CONFIG_CFI_CLANG=y`. The source registers through `module_init`. A future deliberate `CONFIG_NFC_QTI_I2C=y` variant is *Kconfig-plausible* and would compile the guard into the Image, eliminating any need to install the **guarded** separate `.ko`. However, Android's unchanged vendor loader still enumerates the OEM `nfc_i2c.ko`: it could attempt to load a second NFC driver, conflict with the built-in device, or fail and alter loader behavior. **Never claim that merely setting `y` is proven safe, nor that a hypothetical Boot alone fixes the device.** Review built-in/duplicate-driver semantics, CFI, ABI, and recovery rollback before one focused new integrated build/boot validation.

**C. Replace on-partition OEM NFC module inside `vendor_a` EROFS** (direct but presently too risky).
Requires constructing exact dynamic Vendor filesystem image, AVB chained hash-tree/signing strategy, both slot state and full factory rollback. TWRP `adb push /vendor` cannot write EROFS and AVB must not be disabled to shortcut. No safe reproduction/identity exists yet: **NOT AUTHORIZED**.

**D. Unknown root-based systemless overlay**: do not assume Magisk/root or early mount ordering; never present as deployable without grounded device state.

Official references:
- Android first-stage vendor ramdisk modules, `modules.load` and second-stage vendor module location: https://source.android.com/docs/core/architecture/kernel/kernel-module-support
- `vendor_boot` v3/v4 structures: https://source.android.com/docs/core/architecture/partitions/vendor-boot-partitions
- Android `libmodprobe` `finit_module` may treat `EEXIST` as already loaded in upstream versions, but the actual proprietary `/vendor/bin/modprobe` and boot effects remain unverified: https://android.googlesource.com/platform/system/core/+/android16-qpr2-release/libmodprobe/libmodprobe_ext.cpp

## Engineering next gate, user state

Proceed autonomously to **controlled Kconfig/in-tree NFC=y feasibility verification**, especially duplicate vendor module/recovery implications, or preloading a guarded module with a **proof of module load path** before any physical flash. Keep frozen C0059 untouched, no new speculative xHCI patches. When a real one-image/paired-image variant passes all static/KMI/identity/packaging and has a genuine rollback method, provide Artifact, boot SHA, exact CI run and only then mark **`boot打包可準備測試`**. No new Boot generated in this analysis. **No additional TWRP log requested now.**

Status: `STOCK_VENDOR_BOOT_NFC_NOT_PRESENT`, `NORMAL_FIRST_STAGE_ONLY_MSM_DRM`, `VENDOR_BOOT_PLACEMENT_ONLY_NOT_SOLUTION`, `KERNEL_BUILTIN_NFC_FEASIBLE_UNPROVEN`, `MATCHED_DEVICE_DEPLOYMENT_PENDING`.
