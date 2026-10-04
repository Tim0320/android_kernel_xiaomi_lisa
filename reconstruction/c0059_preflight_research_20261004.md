# Candidate0059 preflight research status

This file records the evidence that must be satisfied before Candidate0059 is allowed to start a full kernel build.

## Goal A — Developer Options

Working stock runtime baseline is now treated as:
- ro.debuggable=0
- ro.force.debuggable=0
- ro.secure=1
- ro.adb.secure=1

Candidate0058 runtime diverges to 1/1/0/0 even though the published Candidate0058 boot ramdisk still contains stock-like user values and does not contain force_debuggable, adb_debug.prop, or userdebug_plat_sepolicy.cil.

Boot-order evidence narrows the failure further: vendor_init later tries to apply ro.adb.secure=1 from /vendor/default.prop, but property-service/SELinux denies that write. Therefore the bad ro.adb.secure=0 value already exists before that vendor property file can repair it. The repair must identify the actual earlier source rather than weaken SELinux or grant broad property access.

Current unresolved blocker:
- identify the first early-boot source that creates the 1/1/0/0 runtime state, then restore the stock-equivalent 0/0/1/1 behavior.

Accepted fix classes include a proven correction in the actual boot-chain/debug fragment/init/root overlay source. Global permissive, broad system_app property grants, or fake property success are rejected.

## Goal B — Android16 reconstructed-boot jank

Stock-vs-candidate evidence:
- Stock Lisa: CONFIG_MIHW=y, CONFIG_MIGT=y, CONFIG_PACKAGE_RUNTIME_INFO=y, CONFIG_OEM_KERNEL=y.
- Candidate0058: CONFIG_MIHW=y, but MIGT/PACKAGE_RUNTIME_INFO/OEM_KERNEL are absent.
- Historical stock probes expose migt_init, migt_sched_init, game_load_init, and pkg_init.

Same-generation Xiaomi 5.4 source review shows the dependency chain is not a single-file feature:
- drivers/mihw/migt.c
- kernel/sched/pkg_core.c
- kernel/sched/pkg_interface.c
- kernel/sched/migt_sched.c
- kernel/sched/glk.c
- include/linux/pkg_stat.h
- kernel/sched/Makefile wiring for pkg_core.o, pkg_interface.o, migt_sched.o, glk.o

The Lisa port must therefore be a minimal coherent port after dependency/ABI review. Enabling CONFIG_MIGT without the package-runtime/scheduler plumbing is not accepted.

The Android16 capture also shows an iorapd restart loop because /dev/iorap_dev is absent. Old Lisa stock policy historically disabled iorapd, while newer Xiaomi generations use a real launch-boost/iorap2 ABI. Do not create a fake node or return success for unknown ioctls. Treat this as a separate compatibility decision: stock-faithful disable versus a semantically correct 5.4 implementation only after the caller ABI is proven.

MIGT and Metis are not interchangeable. Old /dev/migt and newer /dev/metis use different command contracts. A direct alias is explicitly rejected.

## No-build gate

Use `reconstruction/scripts/candidate_0059_preflight.py` before creating the full Candidate0059 build workflow.

The gate must fail until all of the following are true:
1. CONFIG_MIHW, CONFIG_MIGT, CONFIG_PACKAGE_RUNTIME_INFO, and CONFIG_OEM_KERNEL are restored in the staged source/config.
2. migt_init, migt_sched_init, game_load_init, pkg_init and the required scheduler objects are present.
3. Candidate runtime debug/security properties match the working stock baseline.
4. The actual early debug-property override source/fix location is documented.
5. No direct MIGT-to-Metis device alias is introduced.

A preflight PASS is not a runtime PASS. Candidate0059 remains device-test-ready only after the later full build/static verification; Developer Options and Android16 jank still require real-device validation.
