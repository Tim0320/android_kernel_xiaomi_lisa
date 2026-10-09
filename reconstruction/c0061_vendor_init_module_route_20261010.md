# Candidate0061 vendor init/module-loading route audit — 2026-10-10

## Input (real device, recovery-based read-only vendor_a capture)

User-uploaded `lisa_nfc_init_logs.zip`: SHA256 `866164c26a20201f4051732e99441525972d3cfced1e2cf2d1adabcd7b623ec0`, **156** vendor `.rc` files, all drawn from the mounted Android vendor filesystem `vendor/etc/init` (not TWRP's own `init`). No changes were made to the vendor partition.

Relevant exact lines:

- `vendor_init/hw/init.target.rc:38–40`: `on early-init`, then `exec u:r:vendor_modprobe:s0 -- /vendor/bin/vendor_modprobe.sh`, then explicit `/vendor/bin/modprobe -a -d /vendor/lib/modules` for a defined Qualcomm audio/DSP driver set. That explicit list does **not** include `nfc_i2c`.
- `vendor_init/hw/init.qcom.rc:421–425`: `service nqnfcinfo /system/vendor/bin/nqnfcinfo`, `class late_start`, `group nfc`, `user system`, `oneshot`. Earlier historical C0061 Oops involved task `nqnfcinfo`, which makes this relationship relevant, but the Oops is not fresh evidence for the most recent boot.
- `vendor_init/vendor.nxp.hardware.nfc@2.0-service.rc:30–33`: `service nqnfc_2_0_hal_service /vendor/bin/hw/vendor.nxp.hardware.nfc@2.0-service`, `class hal`, `user nfc`, `group nfc`.
- A full text scan over all 156 files found **zero** literal `nfc_i2c` and **zero** literal `modules.load`. Thus no captured `.rc` file establishes which of the two 5.4.289 vendor NFC files Android attempts to load; absence of the literal string does not prove the module never loads.
- Three captured `.rc` files mention `modprobe`, showing both `/vendor/lib/modules` and `/vendor/lib/modules/5.4-gki` may be used in different cases. This is conditional path evidence, not NFC-specific loading proof.

## Interpreting the device observations

Previously confirmed device file evidence from TWRP v1.4.0:
- `/vendor/lib/modules/nfc_i2c.ko` with 5.4.289 QGKI vermagic (SHA256 `b37dae41aad83b6adaa1f2a16253d2a8ca931b83a534fd5fb57ceaea2424bc68`).
- `/vendor/lib/modules/5.4-gki/nfc_i2c.ko` with 5.4.289 GKI vermagic (SHA256 `bb1e8994d0ddf0b15bd038457a850b2a8b5c7b74e1816b97dea5623c2ea5c80b`).
- The separate C0061 5.4.302 guarded module is SHA256 `aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b`, compiled but not present in either inspected file.

AOSP references:
- https://source.android.com/docs/core/architecture/kernel/loadable-kernel-modules — early-init can use `modprobe -a -d /vendor/lib/modules`; `CONFIG_MODVERSIONS` checks symbol CRC compatibility with the running kernel.
- https://source.android.com/docs/core/architecture/kernel/kernel-module-support — first-stage init may use ramdisk `/lib/modules/modules.load`; other modules can be under vendor. Seeing vendor `.rc` files alone does not reveal all possible loading paths.

## Highest-value next single device input

Read **only** Android's actual `/vendor/bin/vendor_modprobe.sh` from `/dev/block/mapper/vendor_a` via temporary EROFS `ro` mount in TWRP. Also read `/vendor/lib/modules/modules.load` only if the prior manifest evidence is insufficient, not an entire redundant TWRP ZIP. If the script references additional files, request only those exact files next.

The script may establish the chosen vendor module load directory or delegation, but remains **static intent**, not an actual Android boot `insmod/modprobe` outcome. Evidence of actual loaded module / first contemporary failure still requires Android-side ADB if feasible; otherwise a fresh persistent crash mechanism, not Recovery's `/proc/modules`.

## Status and safety

Classification: `STATIC_VENDOR_INIT_ROUTE_PARTIAL`, `DEVICE_NFC_MODULE_LOADING_UNVERIFIED`, `BOOT_CAUSE_UNRESOLVED`.

Do not flash the separate NFC inspection-only artifact, mutate EROFS/AVB, weaken SELinux/thermal, or recompile the same Direct-302 boot solely to obtain the already-known file evidence.

**Required status reports:** every assistant/scheduled report must show the **latest newly launched relevant GitHub Action URL**, or explicitly `無` if none. If, and only if, an Action has actually produced a gate-verified new boot.img suitable to prepare for device testing, append the exact label **「boot打包可準備測試」** to that Action entry, with artifact ID, boot SHA256, kernel source commit and constraints. Evidence-only / NFC inspection-only runs must never receive that label.
