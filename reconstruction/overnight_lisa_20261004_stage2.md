# Lisa overnight stage 2 - 2026-10-04

Read together with `reconstruction/overnight_lisa_20261004.md`. This adds actual second-audit results, not a new runtime repair. Re-read current CI before treating the build status below as current.

## Candidate0056 still requires completion verification

Candidate0056 source/package: 202d40a1432885b9e3a59c35c7bac8890938d587, Run37147002208, build111272919620, observe111272919758. Last direct read: steps1-8 success, step9 Build and package in progress; final validation/upload pending. Do not publish a new boot or mark battery fixed until actual artifact verification and later device tests.

## Second audit completed successfully

Workflow commit851e827b529b0f938864a9575180fbc813a9ecf9, Run37147557722 SUCCESS, artifact11282767475 `lisa-camera-wlan-ownership-audit`, ZIP SHA2567786466a6eb6f1184c19af85656ab93b3c04e018f14942a073f49f4d8e389332. Independently downloaded, checksum checked and read ownership.json/REPORT.md. Twelve normal-QGKI dependency modules were in the camera/WLAN closure; no missing dependency files.

Public stock OS2.0.3 reference camera.ko imports283 symbols, has0 mismatches for symbols provided by current0055 core, and duplicates73 core exports. Its ELF depends string is **leds-qti-flash only**; the reference module does not import HWID. This differs from the rebuilt donor camera which directly calls HWID getters. Do not incorrectly state the stock binary has the same HWID dependency as rebuilt camera.

Reference HWID:8 imports,0 core CRC mismatch,9 duplicate core exports.
Reference QTI flash:46 imports,0 core CRC mismatch,2 duplicate core exports; depends on qti_battery_charger_main_k8.
Battery:78 imports; the two missing power providers remain the only symbol names unresolved across this reference closure. Its display notifier imports are supplied by msm_drm.
CNSS2/ICNSS2/WLAN variants and their reference dependencies have0 core CRC mismatches and no unresolved symbol names across the closure. This does not establish every inter-module CRC, data-layout or actual OS2.0.8 phone compatibility.

Logical dependency graph:

```
reference camera.ko -> leds-qti-flash.ko -> qti_battery_charger_main_k8.ko -> msm_drm.ko
reference WLAN -> cnss2/icnss2 -> hwid.ko + firmware/QMI-related providers
```

The normal/GKI WLAN modules are attempted by separate exec_background modprobe commands in public init.target.rc. GKI mismatch messages alone need not be the blocker for a correctly loading normal-QGKI branch. The normal branch's actual HWID duplicate-export error is independently observed in the phone log.

### Future independent ownership candidate, NOT implemented here

A coherent experiment could restore stock camera/flash/HWID ownership instead of individually changing HWID=m while donor camera is built-in. Need verify all consumers and replace old built-in-camera gates explicitly with genuine module-import/ownership/load-contract gates; do not just delete checks.

Pinned source6e568a camera root Makefile is guarded by CONFIG_USE_COMMON_CAMERA; both yupikcamera.conf and lahainacamera.conf explicitly export CONFIG_SPECTRA_CAMERA=y. drivers/Makefile uses obj-$(CONFIG_SPECTRA_CAMERA) += camera.o and supports m. Current0053-derived builder promotes HWID/flash to y and injects common-camera environment. A normal global .config edit alone does not control all those make-variable injections.

Pinned cam_soc_util.c HWID conditional is for K11 AF regulator delay; cam_csiphy_core.c conditional targets J18/K2/K3S/K8/K11. Do not remove conditionals blindly: scope any alternative to known Lisa platform and prove no other runtime caller needs the missing symbol. Existing Goodix/touch configuration and any built-in flash use must be reviewed.

Do not implement fake EEXIST/module-load success, strip symbol versions, force GKI modules, or remove protection. Do not assume modules.builtin fixes Android14 libmodprobe: inspected constructor does not read it.

## Additional display evidence

Phone log at02:32:15.362 enumerates display mode1080x2400 at90Hz. At02:32:15.363 it successfully reads max_brightness_clone=4095, then fails opening brightness_clone with Permission denied. This supports a partial feature-node access problem, not total panel absence. The actual node owner/mode/SELinux label is not captured, so cannot distinguish DAC from policy or timing yet.

Exact donor source:
https://github.com/Tim0320/android_kernel_xiaomi_lisa/blob/6e568aabc77a06fa787baec1d9e60e4b559874a3/techpack/display/msm/mi_disp/mi_disp_sysfs.c
Defines DEVICE_ATTR_RW(brightness_clone) and DEVICE_ATTR_RW(doze_brightness); no simple brightness attribute in that specific attribute group. Runtime uses stock msm_drm, so donor source alone is not a byte-for-byte proof of runtime implementation.

Pinned public vendor init:
https://github.com/Jiovanni-dump/xiaomi_lisa_dump/blob/2dbe7b5569ed49cc2c6649a7b313d4a092755034/vendor/etc/init/hw/init.target.rc
Lines276-301 set system:system and0664 for relevant display nodes. Current phone0.8 scripts still need direct validation against this0.3 reference. No blanket chmod777 or permissive mode.

Official AOD FAQ was reverified via current web indexing:
https://www.mi.com/uk/support/faq/details/KA-93156/
It states stock Xiaomi11Lite5GNE AOD turns off after10seconds by design. Some direct fetches of that page error, but indexed official content was retrieved. The specific old crDroid9.8/Silver-kernel60Hz workaround remains a different context, not a current HyperOS prescription:
https://t.me/s/mi11litene?q=%23crDroid (2023-09-01 release).

## Continued work

Finish0056 artifact verification, record actual first failure if any, then use this evidence to plan isolated WLAN ownership repair. The scheduled hourly task remains enabled; morning report after08:00Taipei should distinguish passed audits, submitted code, verified build and untested hardware. If only device tests remain after the morning handoff, stop the same task explicitly. No new automated phone flashing or second task.
