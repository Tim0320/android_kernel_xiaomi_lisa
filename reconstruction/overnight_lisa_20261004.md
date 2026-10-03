# Lisa overnight handoff - 2026-10-04 (Asia/Taipei)

## Baseline and evidence boundaries

Device-tested baseline: Candidate0055, package `3fa7fb6ba9a65a75d832ca721afb266c6aa8fcdd`, run `37143391425`, artifact `11280923629`. User reports Android stays up but battery and Wi-Fi do not work. Preserve this baseline and its UFS registry/procfs/CFI fixes.

Latest private input: `lisa-live-20261004-023131.zip`, SHA256 `e2d6d9cee51f2dc4833b99e7fb51cf998d7ccf423945343913c93c29209f4634`. Raw input is in the user's ChatGPT files; do not publish raw logs, identifiers, or full properties here. Line references below refer to UTF-8 normalized `logcat_live.txt` (33023 lines). Direct dmesg was denied; this capture ends during framework startup. No claim that the log itself includes full boot completion, a suspend/resume test, or a charging test. Timestamps change when the device clock is synchronized.

## Current fault matrix

| Area | Observed evidence | Status / next step |
|---|---|---|
| Prior UFS/mi-memory crash | L1307 `LISA0055_UFS_REGISTRY stage=bind lun=0 ready=1 host=0`; no kernel NULL/panic/CFI/raw-fault record in this limited capture; user reports no recurring crash | Improved; not a long-duration stability certification |
| Battery/charging | L2479-2480 and repeated: qti_battery_charger_main_k8 cannot resolve `power_debug_print_enabled` and `mi_power_save_battery_cave`; L16423 healthd cannot find battery devices | Confirmed module-load blocker. Recover real provider prototypes and behavior; do not fake charge/capacity values or bypass thermal protection |
| Wi-Fi | L3252ff incompatible 5.4-gki qmi_helpers module_layout; L3315ff hwid load failure; L2508/2925/3261/3362/11095 explicitly show duplicate `get_hw_build_adc` owned by kernel | Confirmed ownership/dependency issue. Baseline has QCOM_QMI_HELPERS=y and MI_HARDWARE_ID=y. Inspect both normal/GKI module metadata and actual hardware selection before modifying |
| Mobile-data dependency | rmnet_ctl exports `rmnet_ctl_if` already owned by kernel; rmnet_core/offload/shs dependencies fail | Confirmed module conflict; end-to-end mobile data not tested; separate from persistent IPA error |
| Display brightness/color | brightness_clone permission denied L8797/8827; L23151 alternate mi_display brightness node absent; PostBlendIGC has zero entries L22708ff; calibration property denied | Partial display integration errors. Basic visible desktop is user-reported; distinguish DAC/SELinux/userspace assets from panel-driver defects |
| AOD/doze | AOD-related sensors initialized and doze bookkeeping exists | Not verified. No sufficient evidence of successful or failed screen-off AOD transition |
| Audio modules | snd_event_dlkm/swr_dlkm/q6_pdr_dlkm/wcd_core_dlkm/us_prox_iio duplicate exports in the core; other audio initialization continues | Module ownership conflicts, but not proof all playback is broken. Keep first audio test separate |
| Camera/flash | Public Lisa dependency graph ties flash/camera to battery driver; camera provider initialization messages exist | Risk from dependencies; no actual capture/flash validation |
| ADB/SELinux | adbd attempts su context, is denied setcurrent, then aborts at L17058ff; another init-named process abort appears at L18578 (PID2066, NOT PID1) | Userspace/security-policy errors. Do not globally permit SELinux or call this a kernel panic |
| IPA | Completed PAS15 auth/reset calls still return -22 | Unresolved separate subsystem problem; retain bridge because previous no-bridge control regressed boot |
| BPF | Network BPF load success in log; BPF/JIT/events enabled in final configuration | Basic Android networking BPF present; not related to missing battery exports |
| Thermal/sensors/fingerprint | Battery telemetry unavailable; sensor/HAL initialization exists but limited exercise | Do not assert fully functional. No unattended charge or thermal stress test recommended while telemetry is missing |

## Source findings (reference, not actual phone bytes)

1. Public Lisa module dependency list, pinned OS2.0.3 global dump (current reported vendor is OS2.0.8 global):
   https://github.com/Jiovanni-dump/xiaomi_lisa_dump/blob/2dbe7b5569ed49cc2c6649a7b313d4a092755034/vendor/lib/modules/modules.dep
   Both cnss2 and icnss2 depend on hwid; qca_cld3_wlan and qca_cld3_qca6750 have different connectivity dependencies. Do not assume every fallback candidate is the actual Lisa hardware path. Battery depends on msm_drm; flash/camera depend on battery.
2. Analogous Mi11 Pro report about the same two battery exports:
   https://github.com/birdnofoots/Mi11Pro-Droidspaces-Kernel-KSU/blob/805e7a0464dd1aded33fdfc42e779660d560e26a/patches/fix-debug-power-mi.py
   This is the author's report for another device, not a validated Lisa repair. Its mi_syms.c contains a guessed no-argument/return-zero capacity stub; DO NOT adopt it.
3. Concrete Xiaomi mi-power implementation on a different platform:
   https://github.com/LowTension/android_kernel_xiaomi_sm8475/blob/39382bf760ccf05a8fb4dddee7138ecac02d4a59/drivers/misc/mi-power/mi_power.c
   https://github.com/LowTension/android_kernel_xiaomi_sm8475/blob/39382bf760ccf05a8fb4dddee7138ecac02d4a59/drivers/misc/mi-power/mi_power.h
   Header says bool power_debug_print_enabled(void). Capacity function is ssize_t mi_power_save_battery_cave(ssize_t capacity): unchanged capacity in normal modes and a defined curve in power-save modes. Not a zero-return function. Do not transplant its whole newer-platform interrupt/power driver into 5.4 without adaptation.
4. Lisa-specific caller reference:
   https://github.com/tew080/Hexagon-kernel-lisa/blob/f97235632013bc2870340665237cc39cc55945d9/drivers/power/supply/qti_battery_charger.c
   Calls the capacity function with the battery property and uses its result. Verify exact stock declaration and CRC before any provider implementation.
5. Official Kbuild documents modules.builtin and modules.builtin.modinfo:
   https://www.kernel.org/doc/html/v6.11/kbuild/kbuild.html
   Actual Android libmodprobe behavior and current vendor metadata must be checked; ordinary kmod documentation alone is not enough to prescribe an Android fix.

## Next Action: contract audit, not a replacement boot

`reconstruction/scripts/lisa_driver_audit.py` is read-only. It validates the existing 0055 artifact, downloads pinned public Lisa reference modules, checks their Git/LFS hashes, parses ELF import CRCs/export owners, and compares normal/GKI module dependency files. It also searches previously captured stock IKHEADERS artifact 10637733529 for real battery prototypes. Artifact `lisa-driver-contract-audit` is reference evidence, NOT a flashable module/boot release.

Local validation: Python syntax passed; ELF parser reads the actual 0055 msm_drm module and correctly identifies its module_layout CRC; malformed ELF rejected. This is not a remote audit completion claim.

After audit: read module-contracts.json and stock-header-symbols.json. Confirm provider ABI against source/callers. Minimal battery provider restoration first if justified; resolve Wi-Fi duplicate built-in ownership and dependency resolution separately. Do not change module_layout CRC or disable checks to force a load. Reverting HWID to m can break the built-in camera/flash dependency that originally motivated promotion; consider the full dependency graph.

## Overnight execution and reporting

Only ChatGPT task 6ab2be5b63348191a2883afc462945b7 is used, hourly. A build's GitHub observe job checks at 2, 2, then 5 minute intervals; it observes, not writes AI patches. Each iteration re-reads main/CI/evidence. Keep this handoff updated with real commit/run/artifact/result. First iteration after 08:00 Taipei reports accumulated findings and attempts. Do not stop on a failed/incomplete build; fix an actionable first blocker. Stop only when a verified candidate artifact exists and remaining work genuinely requires device testing, with an explicit handoff. Never claim any untested driver is repaired or guarantee no future failures.
