# Lisa overnight handoff - 2026-10-04 (Asia/Taipei)

## Current execution state - re-read CI before acting

Device-tested stable-desktop baseline: **Candidate0055, 3fa7fb6ba9a65a75d832ca721afb266c6aa8fcdd**, run37143391425, artifact11280923629. User reports no recurring post-boot crash, but battery and Wi-Fi fail. Do not remove its UFS registry/procfs/CFI fixes.

**Candidate0056 battery-only attempt: 202d40a1432885b9e3a59c35c7bac8890938d587**, run37147002208, build111272919620, observe111272919758. Last read: preflight/preparation passed, build step9 in progress. NO new verified boot or battery runtime pass is claimed yet. Read actual latest result and first blocker, fix minimally if needed.

First read-only contract audit: b1b8bbf45674daa9085a25babc8d4f809de9d143, run37146553558 SUCCESS, artifact11282054888 `lisa-driver-contract-audit`, SHA256 `8e25c7d93bf7ba7b505f9b1e5771aae448df7be3e0597eb99c13545204eaa9f6`.
Second read-only camera/HWID/WLAN ownership audit: script8a459400eaddcbb4e3ba75ee0eaf243bb23e1232, workflow851e827b529b0f938864a9575180fbc813a9ecf9 (`audit-lisa-camera-wlan-ownership.yml`). Read the newest run/artifact `lisa-camera-wlan-ownership-audit`. This audit is not a boot and does not modify runtime code.

## Evidence boundaries

Private input: `lisa-live-20261004-023131.zip`, SHA256 `e2d6d9cee51f2dc4833b99e7fb51cf998d7ccf423945343913c93c29209f4634`. Do not publish full raw logs or device identifiers. Line numbers below refer to normalized UTF-8 logcat_live.txt (33023 lines). Direct dmesg was denied. Capture ends at 02:32:25.611 during framework startup; no full boot-completion, endurance, charging, camera capture or AOD-transition test is contained in this log. The user's desktop observation is separate evidence. Early dates change when the device clock synchronizes.

## Fault matrix

| Area | Observed evidence | Interpretation / action |
|---|---|---|
| Prior UFS/mi-memory crash | L1307 LISA0055_UFS_REGISTRY bind lun0 ready1; no NULL/panic/CFI/raw-fault in limited capture; user says stable desktop | Improved; preserve repair; not endurance certification |
| Battery/charging | L2479-2480,2541-2542,2552-2553 missing power_debug_print_enabled and mi_power_save_battery_cave; L16423 healthd no battery devices | Confirmed provider/module-load blocker; 0056 attempts typed provider restoration |
| Wi-Fi | L3257ff incompatible 5.4-gki qmi_helpers module_layout; normal hwid load fails; L2508/2925/3261/3362/11095 duplicate get_hw_build_adc owned by kernel | Core already contains QMI/HWID. Normal QGKI dependencies and ownership must be aligned; do not force GKI modules |
| Mobile-data dependencies | rmnet_ctl_if already owned by core, then rmnet_core/offload/shs load failures | Confirmed duplicate-provider conflict; end-to-end mobile data untested; separate IPA issue |
| Display brightness/color | brightness_clone EACCES L8797/8827; alternate brightness ENOENT L23151; PostBlendIGC zero entries L22708ff; calibration property denied | Partial userspace/path/permission integration errors, not proof all display is broken; panel works per user |
| AOD/doze | AOD sensor and doze initialization only | Unverified. Stock 10-second AOD behavior is a Xiaomi design limitation, not by itself a kernel failure |
| Audio modules | snd_event/swr/q6_pdr/wcd_core/us_prox duplicate core exports; other audio setup continues | Ownership errors, not proof all playback is broken; test playback/mic/calls separately |
| Camera/flash | Vendor dependency chain camera -> flash -> battery -> msm_drm, plus camera/WLAN -> hwid; camera provider startup exists | Dependency risk; no photo/flash test. Built-in-camera workaround is linked to HWID duplication |
| ADB/security | L17058ff adbd denied su setcurrent, then SIGABRT; another process named init PID2066 aborts L18578 | Userspace errors, not PID1 death or kernel panic. No global permissive policy or chmod777 |
| IPA | 22 INIT_IMAGE=0 records; 21 completed auth/reset=-22 records; last unfinished in capture | Still unresolved. Full0xA000 did not fix it; removing manual bridge previously caused one-screen failure |
| BPF | L7366-7367 Netd networking BPF programs loaded | Present/working for this Android load path; not the battery/WLAN-module root cause |
| Thermal/sensors/fingerprint | HAL startup only; battery telemetry unavailable | Not functionally validated. Avoid unattended charging/thermal stress while telemetry is unavailable |

## First audit - actual artifact results

Compared actual Candidate0055 artifact with pinned **public** `Jiovanni-dump/xiaomi_lisa_dump@2dbe7b5569ed49cc2c6649a7b313d4a092755034` (OS2.0.3 global). Phone currently reports vendorOS2.0.8 global; these public module bytes are NOT claimed to be the phone's exact modules.

28 reference modules were parsed with validated Git/LFS hashes. For normal `/vendor/lib/modules/`:

| Module | Imports | Missing from vmlinux | Core CRC mismatch | Exports duplicated in core |
|---|---:|---:|---:|---:|
| qti_battery_charger_main_k8 |78|4|0|0|
| hwid |8|0|0|9|
| cnss2 |299|57|0|0|
| icnss2 |224|64|0|0|
| qca_cld3_wlan |480|50|0|0|
| qca_cld3_qca6750 |457|34|0|0|
| msm_drm |736|0|0|0|
| leds-qti-flash |46|1|0|2|
| rmnet_ctl |24|0|0|5|

Missing-from-core can mean a legitimate provider in another module; do NOT treat every count as a missing implementation. Battery's two display notifier symbols are exported by msm_drm; the two Xiaomi power functions are genuinely absent in core. Full table, exports, dependency files, prototypes and CRCs are in module-contracts.json / stock-header-symbols.json / REPORT.md in the audit artifact.

The public 5.4-gki modules are a different ABI family: module_layout0x1e5b7ab7 vs0055core0xba39cbb8; qmi_helpers has9 mismatches and14 duplicate core exports. Do not rewrite checksums/version checks to load them. Zero CRC mismatch in the normal set still does not prove all runtime structure layouts.

Exact stock IKHEADERS artifact10637733529 (ZIP SHA256 c62b32b2e411c9795ed4d60a7d1910b1dde8661ea7bbde74e22e23a8dbd54b8f) confirms:
```
bool power_debug_print_enabled(void);
ssize_t mi_power_save_battery_cave(ssize_t capcity);
```
Expected normal battery import CRCs: power_debug_print_enabled0x621d7dcb, mi_power_save_battery_cave0x746eee3e.

## Candidate0056 attempted fix, scope and validation

New files: reconstruction/overlays/lisa_power_compat.c/.h; reconstruction/scripts/candidate_0056_build.py, candidate_0056_power_patch.py, test_lisa_power_compat.c; build-lisa-candidate-0056-power-providers.yml.

This is a **scoped compatibility implementation**, not an exact recovered full OEM power-debug driver. It provides stateful bool debug control and `/sys/class/power_debug/power_mode` (raw0..4). Normal raw modes0/1 return the actual input capacity unchanged. Save modes2..4 use the referenced public Xiaomi mi-power curve. Defensive difference: negative/error or >100 readings pass through, never invent zero/full capacity. No charging voltage/current/thermal/authentication controls are changed. Default rawmode1 matches the referenced driver. Debug sysfs only controls this provider; it does not claim all OEM suspend-debug hooks exist.

Local and CI preflight tests: Python syntax/pinned ancestors; C compile with warnings-as-errors and ASan/UBSan; 505 valid mode/capacity combinations plus extrema/invalid modes. Actual kernel build must naturally produce both expected CRCs, real linked code symbols, compiled object and marker, plus inherited UFS/CFI/display/PAS checks. Never edit CRCs to satisfy the gate.

A successful build is only a candidate to test: battery/power_supply registration, healthd readings, valid temperature, charging transition and no new crash are still required on the actual phone. Wi-Fi and AOD are intentionally not claimed repaired by0056.

## Primary sources and applicability

- Public Lisa dependency list: https://github.com/Jiovanni-dump/xiaomi_lisa_dump/blob/2dbe7b5569ed49cc2c6649a7b313d4a092755034/vendor/lib/modules/modules.dep
- Lisa battery caller uses the capacity argument/result: https://github.com/tew080/Hexagon-kernel-lisa/blob/f97235632013bc2870340665237cc39cc55945d9/drivers/power/supply/qti_battery_charger.c
- Genuine newer-platform Xiaomi mi-power implementation, used only for bounded capacity-mode semantics: https://github.com/LowTension/android_kernel_xiaomi_sm8475/blob/39382bf760ccf05a8fb4dddee7138ecac02d4a59/drivers/misc/mi-power/mi_power.c and mi_power.h. Do not transplant its whole IRQ/platform driver into5.4.
- Analogous Mi11Pro report: https://github.com/birdnofoots/Mi11Pro-Droidspaces-Kernel-KSU/blob/805e7a0464dd1aded33fdfc42e779660d560e26a/patches/fix-debug-power-mi.py . Different device; its mi_syms.c contains a wrong int data symbol and guessed no-argument/zero capacity stub. NOT adopted.
- Android14 actual libmodprobe constructor and InsmodWithDeps: https://github.com/aosp-mirror/platform_system_core/blob/android-14.0.0_r1/libmodprobe/libmodprobe.cpp . Inspected constructor parses aliases/dep/load/options/softdep/blocklist, NOT modules.builtin. Generic kmod docs alone do not justify a fix on this loader.
- Camera source forces direct HWID calls in cam_utils/cam_soc_util.c and cam_csiphy_core.c; pinned source6e568a. Original builder0053 promoted HWID and QTI flash to built-in to satisfy camera. Camera drivers/Makefile supports `obj-$(CONFIG_SPECTRA_CAMERA) += camera.o`, but platform config files also set camera variables; inspect all before a modular control.
- Xiaomi official AOD FAQ: https://www.mi.com/uk/support/faq/details/KA-93156/ (stock AOD10seconds). No successful actual AOD transition exists in current capture.
- Lisa crDroid9.8 maintainer release message (2023-09-01): https://t.me/s/mi11litene?q=%23crDroid says its Silver-kernel build used AOD60Hz because30Hz was unsupported. This is a specific old custom-ROM/kernel combination, NOT a prescribed value for current HyperOS or proof of current panel limitations.

## Next research/repair decisions

1. Finish0056 and independently verify artifact boot SHA, Image/config/layout, both new providers and all inherited gates. Failed/incomplete CI is not completion.
2. Read second ownership audit. Evaluate coherent restoration of stock camera/flash/HWID modular linkage versus a correctly integrated Android dependency resolver. Do not flip HWID=m alone (built-in camera link fails), add fake module success, or disable CRC/CFI. Do not claim modules.builtin alone is enough. No second boot candidate should overwrite0056 before its actual result is recorded.
3. Resolve mobile-data/audio duplicate providers separately; first know which components are built-in and which vendor modules actually need to load.
4. Display: verify node owner/mode/label, real panel doze transitions, calibration assets and requested refresh modes. Fix only proven node/policy contracts; not blanket permissive.
5. Other first-hand forums often concern other devices listed in the author's profile; match the actual thread device and kernel before attributing a fix toLisa. No exact public Lisa reproduction of this particular missing-provider/duplicate-HWID combination has been confirmed.

## Automation and morning handoff

Only task6ab2be5b63348191a2883afc462945b7, hourly, is enabled. GitHub observe does2/2/5minute checks and does not write AI patches. Re-read latest main/CI each iteration and update this document. Before08:00, continue useful non-destructive remaining research after a verified build, not redundant CI reruns. First iteration after08:00Taipei sends cumulative findings, actual attempts/results, candidate short SHA/run/artifact/hash and remaining tests. Keep task active for actionable incomplete/failed work; after morning summary, stop only when remaining tasks genuinely require user device validation. No automatic phone flashing or thermal/calibration/security bypass, and no claim of guaranteed failure-free operation.
