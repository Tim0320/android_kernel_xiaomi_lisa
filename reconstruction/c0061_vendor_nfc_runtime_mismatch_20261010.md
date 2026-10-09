# Candidate0061 device NFC runtime module provenance - 2026-10-10

## Provenance and scope

- Test: `lisa-twrp-iter-0002_20261010-013518_boot_038e35371c97.zip`, collector **v1.4.0** on Xiaomi lisa, HyperOS 3.0.9 / Android 16, slot `_a`.
- User's observation recorded in ZIP: `進system層後閃退` (progress into the system layer, then crash/reboot); do not paraphrase it as first-screen-only failure.
- Tested boot SHA256: `038e35371c9705fd44908157ce456576100dfcb07f14ef60aa31e3b669c2eed6`.
- Recovery **read-only** EROFS mount: `/dev/block/mapper/vendor_a` via `/tmp/lisa_VENDOR_BASE-ro`; `raw/23` transport=`adb_push_tmp_sh`, exit_code=0.
- `raw/22` adbd provenance exit_code=0. Its root-labelled `service adbd` from `/system/etc/init/hw/init.rc` belongs to **recovery** (`--device_banner=recovery`), not proof that Android's adbd entered a privileged branch.

## Observed Android vendor modules (partition file evidence only)

| Device path | SHA256 | Embedded vermagic |
| --- | --- | --- |
| `/vendor/lib/modules/5.4-gki/nfc_i2c.ko` | `bb1e8994d0ddf0b15bd038457a850b2a8b5c7b74e1816b97dea5623c2ea5c80b` | `5.4.289-g5987d69e25da SMP preempt mod_unload modversions aarch64` |
| `/vendor/lib/modules/nfc_i2c.ko` | `b37dae41aad83b6adaa1f2a16253d2a8ca931b83a534fd5fb57ceaea2424bc68` | `5.4.289-qgki-g5987d69e25da SMP preempt mod_unload modversions aarch64` |

Both corresponding text `modules.dep` and `modules.load` manifest files list `nfc_i2c.ko` in their respective directories. Manifest membership is **not** evidence of Android loading either module.

## Verified Candidate0061 compile artifact

Source: integrated Direct-302 GitHub Action [run 37655937871](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/37655937871), evidence artifact `11500359180`, file `candidate-0061-runtime-modules/nfc_i2c.ko`.

- Module SHA256: `aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b`.
- `modinfo` vermagic: `5.4.302-qgki-lisa-c0061-rfb3b3c2-by-Tim0320 SMP preempt mod_unload modversions aarch64`.
- Module contains NFC cdev guard marker `NFC cdev unavailable`.
- Target kernel release: `5.4.302-qgki-lisa-c0061-rfb3b3c2-by-Tim0320`.
- The fixed-region `boot.img` packages the kernel Image while preserving stock ramdisk/AVB regions. **It does not replace vendor/odm module files.**

## What the new evidence proves and does not prove

**Proven:** the device vendor partition contains two 5.4.289 NFC modules with hashes different from the guarded 5.4.302 CI module. The guarded NFC runtime fix **has not been installed into either observed vendor module file**. A mismatch of on-partition module provenance exists.

**Not proven:** which module, if any, Android actually loaded at the failed boot; whether vermagic differences alone prevented module loading; whether the device's failure was caused by NFC; or whether the earlier `nfc_dev_open` Oops recurred. A previous 5.4.302 NFC Oops in historical logs must not be treated as proof of this boot's first fault.

**Persistence audit:** Oops SHA256 `5e29f593cfa25b166e28bea8082157544891d34558929531e4fcd3303d20701d` and Logdump SHA256 `08cf91fa91ba50db1e55bb54fa1d7efda2cee491c97e2f7fd7f1160d2d825f9a` are unchanged across the Oct 10 captures. Pstore empty and recovery last_kmsg is historical. This capture did not establish a fresh attributable Kernel Oops. Historical Android dropbox/tombstones are dated Oct 5-6, not the Oct 10 attempt.

## Next technical gate (no more blind same-boot captures)

1. Select a **reversible, verified matched-module deployment route** suitable for Android 16 on lisa. Since `vendor_a` is EROFS, `adb push /vendor/lib/modules/nfc_i2c.ko` is not an installation method. Do not mount it read-write or modify dynamic partitions in a blind script.
2. Verify `nfc_i2c.ko` and kernel release, `modversions`/symbol CRC compatibility, correct Android module-loading path, manifests and AVB implications before offering any deployment package. Avoid changing unrelated vendor modules.
3. Stage/test kernel+module as a **pair**, preserving Candidate0059 source and untouched user data. Require explicit rollback/backup strategy for any recovery/partition mutation. Device side evidence must distinguish loaded module from on-partition file and capture the first contemporary fault.
4. The exact existing CI module may be used for packaging review without recompiling the same kernel. Do not claim a new boot or Android success unless it is actually proven.
5. Proceed to WALT / touch / MIGT only after the boot and module deployment condition is addressed.

Classification: `ABI_MODULE / PACKAGING`; **not** `NFC_RUNTIME_PASS`, **not** `DEVICE_BOOT_PASS`.

