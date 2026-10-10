# Candidate0061 first contemporary Android fault: bounded ADB collection gate

Date: 2026-10-10 Asia/Taipei. Evidence classification: `DEVICE_FIRST_FAULT_REQUIRED`; **not** boot test pass.

## Why a new device observation is finally justified

Known facts from authentic device EROFS/read-only files:
- Stock QGKI NFC `nfc_i2c.ko` has 71/71 imported CRC matches with 5.4.302 `vmlinux`; GKI alternative has 32/68 CRC mismatches. This does **not** establish which is loaded.
- The actual `vendor_modprobe.sh` chooses a single first non-blacklisted QGKI `modprobe -l` candidate then switches the entire later batch to `/vendor/lib/modules/5.4-gki` only if that initial QGKI probe fails. Shell bare `wait` can hide background modprobe errors.
- GKI manifests include 7 USB .ko names with capabilities configured built-in on BOTH C0059 and C0061. The Direct-302 vs C0059 build has 5 xHCI vmlinux CRC changes but no proof stock OEM .ko imports them. The old historical Oops/Logdump hashes remained unchanged across TWRP captures and do not establish the current Android first-fault.
- Android `modprobe -l` list order is **not** the first line of `modules.load`. Android upstream implementation enumerates the module dependency map. Source: https://android.googlesource.com/platform/system/core/+/android16-qpr2-release/libmodprobe/libmodprobe.cpp .
- Android official logcat: `adb logcat -b all -v threadtime` can collect active userspace buffers and crash/system logs; requires functioning *Android* ADB, not Recovery ADB. Source: https://developer.android.com/tools/logcat .

## Targeted read-only live capture (new, no same Boot reflashing)

New PowerShell host-side probe: `scripts/collect_lisa_android_first_fault.ps1`, version **v1.0.0**, commit `94c3299`. The user mandated working dir is `D:\1.ROM_Prot\lisa\pull_log` for all commands/output. Script:
1. Polls `adb -d get-state` up to 120s (configurable 15–600) from *before* TWRP **Reboot System**. Only exact `device` counts as Android; `recovery`, `unauthorized`, `offline`, and no ADB are excluded. Existing Candidate0061 must already be installed for this trial; script never flashes.
2. Upon first Android `device`, begins read-only streaming `logcat -b all -v threadtime`, snapshots logcat buffers, `/proc/modules`, basic boot properties and dmesg if permitted. No root, writes, `logcat -c`, insecure operations or changing vendor/AVB.
3. Emits a timestamped folder+private ZIP; `ANDROID_ADB_NOT_OBSERVED` means **no Android runtime evidence** and cannot be passed off as boot success; `ANDROID_ADB_OBSERVED` only means ADB appeared, **not** completed boot.
4. `logcat` can contain personal/private app data; ZIP goes to private chat only and never public GitHub.
5. Distinguishes CI parser/classifier self-test from actual Windows/TWRP/Android runtime validation. CI [#38060440979](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38060440979) **SUCCESS**, including PowerShell parse and `-SelfTest` where `recovery` is rejected; it does **not** validate access to real Android ADB or capture any phone log. Workflow change commit `5a006ab`.

## Next boundary

Pause **same unique** Lisa automation `6ac29deeada88191891ff651309f5641` while user obtains one targeted Android host live capture; resume the same automation when ZIP arrives or user asks to continue. If the device never exposes Android ADB, report `NOT_OBSERVED`, do not claim USB/loader conclusion. Then consider existing crash persistence and reversible instrumentation options without blind repeating same image.

No new Kernel Build, no new boot.img, and no Action has yet earned `boot打包可準備測試`.
