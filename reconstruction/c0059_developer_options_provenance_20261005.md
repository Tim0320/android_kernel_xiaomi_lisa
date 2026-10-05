# Candidate0059 Developer Options provenance update

## New controlled comparison

Candidate0057 fa96c94 was captured with the same reconstructed kernel identity on two environments:

- User A (Android14): ro.debuggable=1, ro.force.debuggable=1, ro.secure=0, ro.adb.secure=0.
- User B (Android16): ro.debuggable=0, ro.force.debuggable=0, ro.secure=1, ro.adb.secure=1.

Both captures still show vendor_init being denied when it tries to set ro.adb.secure=1 from /vendor/default.prop. Therefore that later SELinux denial is not sufficient to create the bad runtime state.

This also proves the reconstructed kernel identity alone is not sufficient to force the 1/1/0/0 property state.

## Boot-chain exclusions already established

The published Candidate0058 boot ramdisk is byte-identical to the healthy stock ramdisk and contains stock-like user properties. It has no force_debuggable, adb_debug.prop, or userdebug_plat_sepolicy.cil.

User A's captured vendor_boot_a_live.img is vendor_boot header v3 with one vendor ramdisk. Its vendor cmdline contains buildvariant=user; whole-image string inspection finds no force_debuggable, adb_debug.prop, debug_ramdisk, or explicit ro.secure=0 override.

Thus Goal A now needs one decisive comparison: hash and inspect the actual boot partition running on User A. Published CI artifact equality does not prove the image on-device was not patched or overlaid after download.

## Read-only collector

Use reconstruction/tools/collect_c0059_boot_provenance.ps1.

For Candidate0058 e476b67, the expected published boot SHA256 is:

f8044eeeacbfe6477d9d5090925339a10c7346f0feb4851d9e292494eac1c946

The collector records:
- live boot_<slot> and vendor_boot_<slot> hashes when root read access exists;
- /proc/cmdline, /proc/bootconfig, PID1 executable and mountinfo;
- /force_debuggable, adb_debug.prop, userdebug_plat_sepolicy.cil, /debug_ramdisk, /first_stage_ramdisk;
- root/resetprop/module indicators without modifying them.

If the live boot hash differs from the published Candidate0058 artifact, Goal A must first explain that mutation. If it matches, the next investigation is the first-stage property/init path on User A rather than changing kernel SELinux or faking property success.


## 2026-10-05 public-source correlation and prepared repair

Public AOSP behavior now narrows the failure further:

- SettingsLib AbstractLogpersistPreferenceController is available only when `ro.debuggable=1`.
- AOSP `adb_debug.prop` sets `ro.adb.secure=0`, `ro.debuggable=1`, and `ro.force.debuggable=1`, but it does not set `ro.secure=0`.
- Public ADB-root/resetprop scripts commonly force the complete `ro.debuggable=1 / ro.force.debuggable=1 / ro.secure=0 / ro.adb.secure=0` state.
- A public Adb-Root-Enabler issue shows the same `logd.logpersistd` access denial followed by an AbstractLogpersistPreferenceController Settings fatal.

References:
- https://android.googlesource.com/platform/frameworks/base/+/d12e150f7a1921bae738791e37950fb8ffdeafb3/packages/SettingsLib/src/com/android/settingslib/development/AbstractLogpersistPreferenceController.java
- https://android.googlesource.com/platform/system/core/+/master/rootdir/adb_debug.prop
- https://github.com/anasfanani/Adb-Root-Enabler/issues/8

This does not prove a specific module is present on User A, but it raises external resetprop/ADB-root property override above speculative kernel/SELinux causes.

Prepared repository artifacts:
- `reconstruction/c0060_devoptions_release_fix_20261005.md`
- `reconstruction/tools/repair_lisa_developer_options.ps1`

The repair tool is read-only by default. Apply mode only disables/backups explicit external files that contain the bad property overrides. It does not weaken SELinux, patch Settings, fake property-service success, or perform live resetprop.

Candidate0059 remains frozen for device comparison; this preparation is for the next repair iteration and must be device-validated before declaring the Developer Options issue solved.
