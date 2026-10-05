# Candidate0060 Developer Options release-property repair

Prepared: 2026-10-05

## Failure signature already observed

Android14 / HyperOS Candidate0058 showed:
- ro.debuggable=1
- ro.force.debuggable=1
- ro.secure=0
- ro.adb.secure=0
- com.android.settings fatal in DevelopmentSettingsDashboardFragment
- AbstractLogpersistPreferenceController accesses logd.logpersistd and persist.logd.logpersistd.buffer
- system_app is denied logpersistd_logging_prop

The working user/release baseline is:
- ro.debuggable=0
- ro.force.debuggable=0
- ro.secure=1
- ro.adb.secure=1

## Public-source root-cause constraints

AOSP SettingsLib exposes LogPersist only when ro.debuggable=1. Therefore a user build that is unexpectedly forced to ro.debuggable=1 enters a controller path that ordinary release SELinux policy is not intended to grant.

AOSP adb_debug.prop explains this three-property debug signature:
- ro.adb.secure=0
- ro.debuggable=1
- ro.force.debuggable=1

It does NOT set ro.secure=0.

The complete 1/1/0/0 tuple is common in ADB-root/resetprop scripts, which explicitly force ro.secure=0 as well. A public Adb-Root-Enabler issue reproduces the same logd.logpersistd access-denied -> AbstractLogpersistPreferenceController -> Settings fatal chain.

References:
- https://android.googlesource.com/platform/frameworks/base/+/d12e150f7a1921bae738791e37950fb8ffdeafb3/packages/SettingsLib/src/com/android/settingslib/development/AbstractLogpersistPreferenceController.java
- https://android.googlesource.com/platform/system/core/+/master/rootdir/adb_debug.prop
- https://android.googlesource.com/platform/system/core/+/refs/tags/android-vts-12.0_r16/init/init.cpp
- https://github.com/anasfanani/Adb-Root-Enabler/issues/8

## Important Lisa evidence

Do not incorrectly blame the Candidate0059 kernel or weaken SELinux:

1. Candidate0058 published boot ramdisk is byte-identical to the healthy stock ramdisk.
2. It contains no force_debuggable, adb_debug.prop or userdebug_plat_sepolicy.cil.
3. User A vendor_boot was buildvariant=user and no direct debug-property marker was found.
4. The same reconstructed kernel identity on Android16 produced the correct 0/0/1/1 tuple.
5. Working stock and reconstructed boots were both unlocked/orange, so AVB orange state alone is not sufficient.

This makes an external property override / root-service / resetprop path the highest-value target until a Candidate0059 device capture proves otherwise.

## Repair policy

The repair must:
- preserve enforcing SELinux;
- preserve release property semantics;
- never grant system_app broad logpersistd property access;
- never patch Settings to ignore a failed property set;
- never fake property-service success;
- never use a kernel/BPF workaround for a userspace property override.

## Prepared repair tool

Use:
reconstruction/tools/repair_lisa_developer_options.ps1

Default mode is read-only. It:
- records the four debug/security properties;
- records build type/tags;
- scans /data/adb module property files and boot-service scripts;
- scans /data/local.prop;
- reports only files that explicitly attempt to force the bad debug/security properties.

Apply mode:
- disables a Magisk-style module only when one of its files explicitly contains a bad property override;
- renames standalone /data/adb service or post-fs-data scripts containing the override;
- backs aside /data/local.prop when it contains the override;
- does NOT run live resetprop;
- does NOT change SELinux;
- does NOT automatically reboot.

This is intentionally targeted: if no external override is found, the tool leaves the device unchanged and the first-stage property source remains unresolved.

## Post-repair acceptance

After reboot, Candidate0060/0059 device evidence must show:
- ro.debuggable=0
- ro.force.debuggable=0
- ro.secure=1
- ro.adb.secure=1
- Developer Options opens repeatedly
- no Access denied finding property logd.logpersistd
- no logpersistd_logging_prop AVC denial associated with Settings
- no AbstractLogpersistPreferenceController fatal

Until a real-device capture passes these checks, the repair is prepared but not device-proven.
