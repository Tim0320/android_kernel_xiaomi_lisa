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
