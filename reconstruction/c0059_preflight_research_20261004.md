# Candidate0059 preflight research status

## Current repository state

Candidate0059 remains a two-fix build. Full CI59 is blocked until the prebuild gate passes for both Developer Options and Android16 performance. This document records the latest narrowed evidence and explicitly separates prebuild evidence from post-device acceptance.

## Goal A — Developer Options

The working stock runtime baseline is confirmed as:
- ro.debuggable=0
- ro.force.debuggable=0
- ro.secure=1
- ro.adb.secure=1

Candidate0058 runtime diverges to 1/1/0/0.

The published Candidate0058 boot artifact was unpacked directly. Its boot ramdisk SHA256 is `0dc218f3167e560444634a6a8cf969eb4470bcf452837a3e23bf45ea0a6819ae`, matching the healthy stock boot ramdisk used by the reconstruction flow. Its ramdisk still contains stock-like user values and no `/force_debuggable`, `adb_debug.prop`, or `userdebug_plat_sepolicy.cil`.

The fixed-region repack also gates header, ramdisk, non-kernel bytes, AVB metadata and footer byte-exact. Therefore the current evidence does **not** support blaming a changed Candidate0058 boot ramdisk.

Stock and Candidate0058 also share the examined SELinux/debug/cmdline knobs, including `CONFIG_SECURITY_SELINUX_DEVELOP=y`, `CONFIG_DEBUG_KERNEL=y`, and the same command-line mode. Those are not candidate-only differences and must not be disabled as a speculative fix.

AOSP debug-ramdisk behavior gives a useful signature: `adb_debug.prop` sets `ro.adb.secure=0`, `ro.debuggable=1`, and `ro.force.debuggable=1`. Candidate0058 matches that triplet, but it also has `ro.secure=0`, which that AOSP debug property file does not explain. The final repair therefore must prove both:
1. the first path that creates the debug triplet; and
2. the independent source of `ro.secure=0`.

Later boot logs show `vendor_init` trying to set `ro.adb.secure=1` from `/vendor/default.prop` and being denied by property-service/SELinux. This proves the bad zero exists earlier, but it does not identify the original source.

Prebuild acceptance for Goal A requires a structured evidence record with:
- resolved=true
- first_override_path_proven=true
- ro_secure_zero_source_resolved=true
- override_source
- fix_location
- source_evidence
- affected_files

Forbidden fixes remain: global permissive, broad `system_app` property grants, fake property-service success, or kernel/BPF workarounds for a userspace property-policy mismatch.

Post-device acceptance requires candidate runtime properties to return to 0/0/1/1 and Developer Options to open repeatedly without the logpersistd property denial or Settings fatal exception.

## Goal B — Android16 performance

The stock-vs-candidate difference remains strong:
- Stock Lisa: `CONFIG_MIHW=y`, `CONFIG_MIGT=y`, `CONFIG_PACKAGE_RUNTIME_INFO=y`, `CONFIG_OEM_KERNEL=y`.
- Candidate0058: MIHW remains, but MIGT, PACKAGE_RUNTIME_INFO and OEM_KERNEL are absent.
- Historical stock probes expose `migt_init`, `migt_sched_init`, `game_load_init`, and `pkg_init`.

Same-generation Xiaomi 5.4 source review shows that PACKAGE_RUNTIME_INFO is broader than one driver plus four scheduler objects. It touches scheduler/task/user lifecycle and accounting plumbing, including package runtime hooks and WALT-related paths. The donor tree references include:
- drivers/mihw/migt.c
- kernel/sched/pkg_core.c
- kernel/sched/pkg_interface.c
- kernel/sched/migt_sched.c
- kernel/sched/glk.c
- include/linux/pkg_stat.h
- scheduler Makefile wiring
- task/user/fork/exit/cred/sysctl/cpuset/timekeeping/cpufreq-schedutil integration points

The pinned Lisa source does not expose these package-runtime/MIGT markers in the already-inspected corresponding files, and its WALT implementation path must be located before hook mapping is complete. Therefore simply copying `migt.c` or toggling `CONFIG_MIGT=y` is not accepted.

The Android16 capture also contains an `iorapd` restart loop because `/dev/iorap_dev` is absent. Old Lisa stock behavior historically disabled iorapd, while newer Xiaomi launch-boost/iorap2 uses a real multi-command ABI. Candidate0059 must choose one explicit policy:
- `stock-faithful-disable`
- `semantic-5.4-port`
- `defer-outside-c0059`

Fake device nodes and unknown-ioctl-success shims are forbidden. Old `/dev/migt` and newer `/dev/metis` are also different ABIs and must not be aliased.

## Two-stage gate

`reconstruction/scripts/candidate_0059_preflight.py` now has two phases.

### prebuild

This phase is allowed to pass before a Candidate0059 device exists. It checks:
- required stock-proven performance config
- MIGT/package-runtime source and scheduler wiring
- working stock runtime property baseline
- resolved Developer Options early-boot provenance/fix location
- explicit iorap strategy
- no direct MIGT/Metis alias

A prebuild PASS only permits one full Candidate0059 build. It is not runtime proof.

### postdevice

This phase is run only after a real Candidate0059 boot has been collected. It re-runs prebuild requirements and additionally checks:
- candidate runtime properties match the working stock baseline
- no logpersistd property denial remains
- no Settings fatal remains in the Developer Options path

Android16 jank still requires the existing same-workload collector and measurable before/after reduction; this script intentionally does not fabricate that runtime measurement.

## Build scope

Candidate0059 must retain Candidate0058 BPF StageA, Candidate0057 Wi-Fi ownership, Candidate0056 battery, Candidate0055 UFS, CFI/MODVERSIONS, display736, PAS/boot-layout/checkpoint/identity gates. Do not mix in BPF StageB-F, F2FS, 5.4.302, IPA experiments, or new display experiments.
