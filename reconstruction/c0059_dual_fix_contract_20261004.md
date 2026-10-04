# Candidate0059 dual-fix contract

Candidate0059 must not be started as a full kernel build until BOTH repair tracks below have source-level fixes and preflight gates. Do not spend another ~30 minute compile on a one-sided candidate.

## Goal A — Developer Options must behave like the original working boot

Observed on Candidate0058 e476b67 (Android14 OS2.0.8.0.UKOMIXM):
- com.android.settings crashes in DevelopmentSettingsDashboardFragment.
- AbstractLogpersistPreferenceController accesses logd.logpersistd / persist.logd.logpersistd.buffer.
- system_app is denied read/set of logpersistd_logging_prop.
- Runtime properties are user/release-keys but ro.debuggable=1, ro.force.debuggable=1, ro.secure=0, ro.adb.secure=0.

Important artifact fact:
- The published Candidate0058 boot ramdisk itself contains ro.secure=1, ro.adb.secure=1, ro.debuggable=0.
- No /force_debuggable, adb_debug.prop or userdebug_plat_sepolicy.cil is present in that boot ramdisk.
- Therefore do not claim the fixed-region repack directly writes those debug runtime properties. Find the actual override source (other boot-chain ramdisk/vendor_boot debug content, root/resetprop/module/init overlay, or another runtime path).

Public Android behavior matches the failure:
- SettingsLib exposes LogPersist only when ro.debuggable=1.
- platform sepolicy grants system_app logpersistd_logging_prop set access only in userdebug/eng.
- A public Adb-Root-Enabler issue reproduces the same logd.logpersistd denial -> AbstractLogpersistPreferenceController crash chain.

Candidate0059 acceptance:
1. Preserve stock/release SELinux semantics; no global permissive and no broad system_app property allow.
2. Preserve the working original boot's effective user properties. Prefer runtime ro.debuggable=0, ro.force.debuggable=0, ro.secure=1, ro.adb.secure=1 if the original working boot confirms those values.
3. Add build evidence that boot ramdisk/debug fragments do not silently add force_debuggable/adb_debug.prop/userdebug policy.
4. Real-device Developer Options must open repeatedly without com.android.settings fatal exception or logpersistd property denial.
5. If the override is external to the CI boot (for example a root/resetprop module), report that explicitly rather than fabricating a kernel fix.

## Goal B — Android16 performance regression introduced by reconstructed boot

User B reports the stock/original boot is smooth while reconstructed candidates are severely janky on the same Lisa lower-level platform.

Measured reconstructed-boot evidence:
- SystemUI jank ~16.58% in the collected 0057 Android16 sample.
- CPU is not simply stuck at low frequency and Thermal Status was 0.
- /dev/metis, /dev/migt and /sys/module/metis are absent in the collected reconstructed-boot sample.
- TurboSched v2/coreApp/top20/Gaea paths are enabled and repeatedly try the unavailable performance interface.
- Perf/FPS hints and some old schedtune task-profile requests fail repeatedly.

Strong stock-vs-candidate kernel difference:
- Exact stock Lisa IKCONFIG contains CONFIG_MIHW=y, CONFIG_MIGT=y, CONFIG_PACKAGE_RUNTIME_INFO=y and CONFIG_OEM_KERNEL=y.
- Candidate0058 embedded config contains CONFIG_MIHW=y but CONFIG_MIGT, CONFIG_PACKAGE_RUNTIME_INFO and CONFIG_OEM_KERNEL are absent.
- Historical stock symbol/initcall diagnosis explicitly includes migt_init, migt_sched_init, game_load_init and pkg_init among stock-only initcalls.
- Public same-generation Xiaomi 5.4 sources provide drivers/mihw/migt.c plus package-runtime/migt scheduler hooks; use them only as lineage references until Lisa ABI/source dependencies are mapped.

Candidate0059 acceptance:
1. Restore the stock-proven Xiaomi performance runtime dependency chain needed by Lisa, including MIGT/package-runtime hooks when source/ABI review proves compatibility.
2. Do NOT create a fake /dev/metis alias and do NOT return success for unknown Metis ioctls. Capture/derive the actual Android16 caller contract before any compatibility bridge.
3. Keep WALT/uclamp/cgroup/cpuset behavior coherent; do not solve lag by pinning max frequency or disabling thermal controls.
4. Keep all Candidate0058 BPF Stage-A, Wi-Fi, battery, UFS, CFI/MODVERSIONS, display and ownership gates.
5. Real-device Android16 comparison must use the same workload and collector before/after. Pass requires a measurable reduction in SystemUI/Settings jank and removal/reduction of the specific performance-interface failure loop without new thermal, battery, radio or stability regressions.

## Build policy

- Candidate0059 is a runtime-change build, so it requires a new compile and a new release identity once both patches are ready.
- Before the full build, run source/ABI/preflight tests for both Goal A and Goal B.
- Preserve the save-before-verify pipeline: upload UNVERIFIED boot + reusable checkpoint before independent validation.
- Do not add more BPF5.10 stages, F2FS changes, 5.4.302 upgrade, IPA experiments or display experiments to Candidate0059.
- Candidate0057 fa96c94 remains the known working fallback for Wi-Fi/battery.
