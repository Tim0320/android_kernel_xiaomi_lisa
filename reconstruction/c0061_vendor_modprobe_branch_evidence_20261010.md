# Candidate0061 vendor module loader branch evidence (2026-10-10)

## New grounded input

User-uploaded `lisa_nfc_loader.zip` (ZIP SHA256 `3a39c7aa9ec83900de764064dde663b56c269c593277419d16e53e941d4d8f79`) contains one 1429-byte `vendor_modprobe.sh`. It was retrieved from Android `vendor_a` via TWRP read-only mount (not Recovery's init). The script includes a Qualcomm proprietary header; preserve only the following abstracted findings, **do not republish the script verbatim**. `bash -n` and `dash -n` succeed on the supplied file; neither check executes its Android vendor-only commands.

## Verified branch mechanics from this specific file

1. `early-init` executes the vendor script, per the previously captured Android vendor `init.target.rc`.
2. Preferred module directory is `/vendor/lib/modules/` (device NFC file: 5.4.289 QGKI). The alternative is `/vendor/lib/modules/5.4-gki` (device NFC file: 5.4.289 GKI).
3. The script asks Android `/vendor/bin/modprobe` to `-l` modules in the preferred directory and uses `modules.blocklist` to select the first nonblocked name.
4. The fallback decision is **only based on the return code of a probe load of that initial selected module**. A nonzero status switches the *entire subsequent batch* to the GKI directory; otherwise it remains in QGKI. This is not per-NFC fallback and does not prove NFC was loaded.
5. Remaining modules are attempted from the selected directory, most in the background; the script waits on the background jobs. A later individual NFC or unrelated load failure does **not** cause re-selection of the other directory.
6. There is no kernel-release/vermagic test and no use of the 5.4.302 guarded NFC build in this vendor script. Both candidate on-device NFC files still have 5.4.289 vermagic.

**Implications:** On the C0061 5.4.302 boot, the Android init script can choose either a QGKI or a GKI directory **but neither observed directory contains the CI 5.4.302 guarded NFC module**. Other vendor modules, not just NFC, may have compatibility risks. The existence of this conditional path is high-confidence static source evidence. The actual branch taken in the failed boot, exact failing module, module load success/rejection and contemporaneous first fault remain **unobserved**. Do not diagnose NFC as the cause of reboot without Android runtime logs. Vendor modules may load with appropriate ABI despite differing release labels, so do not equate a release difference with an inevitable fatal load failure.

## Mechanism corroboration (official upstream, not Lisa boot proof)

- AOSP kernel module location and loading via init / vendor ramdisk: https://source.android.com/docs/core/architecture/kernel/kernel-module-support
- AOSP module versioning & `CONFIG_MODVERSIONS` symbol CRC checks: https://source.android.com/docs/core/architecture/kernel/loadable-kernel-modules
- Android16 first-stage init has its **independent** ramdisk module loader, which can select release-matching `/lib/modules` before vendor `early-init`. Do not conflate the two: https://android.googlesource.com/platform/system/core/+/android16-release/init/first_stage_init.cpp
- AOSP modprobe implementation supports `-d`, `-l`, `-b` semantics, but binary version on this device is not read back: https://android.googlesource.com/platform/system/core/+/android16-qpr2-release/toolbox/modprobe.cpp

## Narrow next evidence (read-only)

From current TWRP `adb get-state=recovery`, mount mapped `/dev/block/mapper/vendor_a` as EROFS ro and retrieve:
- `lib/modules/modules.blocklist`, `lib/modules/modules.load`, `lib/modules/modules.dep`
- `lib/modules/5.4-gki/modules.blocklist`, `lib/modules/5.4-gki/modules.load`, `lib/modules/5.4-gki/modules.dep`
These are **static** configuration/provenance files, not proof of actual Android-loaded branch. The earlier TWRP v1.4.0 report only included individual NFC manifest matches, not complete module lists/blacklists.

If system ADB=device is available even briefly at reboot, prefer **real Android** `logcat -b all`, `/proc/modules`, `dmesg` if permitted, capturing first `init/modprobe/nfc/Unknown symbol/disagrees about version of symbol/Invalid module format/watchdog` lines with timestamps. Never use Recovery `dmesg` as Android boot evidence.

Do not copy the 5.4.302 `nfc_i2c.ko` into EROFS/AVB vendor, use the inspection-only staging archive as flashable, fake module outcomes, turn off SELinux/thermal or rebuild identical boot without a rooted hypothesis. Need matched **whole module set** / dependency and CRC assessment and a reversible, explicitly verified deployment before any device flash.

## Gate / action reporting

- Latest integrated Kernel+Boot static CI reference: `37655937871` (success, but real device crash not fixed).
- NFC module inspection-only staging: `37967884526` artifact `11634242690`; **not flashable**.
- For any **new** run report exact Action URL; if no new Action report `無`. Append `boot打包可準備測試` only when that exact run has a new passing, independently confirmed boot package suitable for test.
- Source classification: `VENDOR_MODPROBE_BRANCH_STATIC_CONFIRMED`; still `ANDROID_ACTUAL_LOAD_UNVERIFIED`, `CURRENT_BOOT_FIRST_FAULT_UNVERIFIED`.
