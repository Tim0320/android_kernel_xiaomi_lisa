# Candidate0059 semantic hook map

This map is for the Android16 performance repair track only. It is a no-build, no-runtime source-port contract.

## Confirmed layout difference

Exact source audit confirms:
- Lisa target `6e568aabc77a06fa787baec1d9e60e4b559874a3` uses split WALT at `kernel/sched/walt/walt.c`.
- Donor `LeviMarvin/android_kernel_xiaomi_alioth@e7065bc9ead4a0ca183f51101e07dd45a9d5c558` uses flat `kernel/sched/walt.c`.
- Raw donor patch application is forbidden; the port must be semantic.

## ABI constraint

The donor directly embeds `struct package_runtime_info pkg` into both `task_struct` and `user_struct`.

Lisa instead has Android KABI reserve slots in these structures. Candidate0059 must not append donor fields directly. The port has to use the Android KABI reserve mechanism only after structure size/alignment and stock ABI implications are proven. This is a hard gate because existing Wi-Fi/display/vendor modules depend on the current kernel ABI contract.

## Semantic landing points

1. Task lifecycle: donor initializes/removes package list state in fork/exit and moves membership across credential transitions. Lisa has corresponding `copy_process`, `release_task`, and `commit_creds` landmarks.
2. Scheduler monitor: donor declares `migt_monitor_hook` in scheduler core. Lisa must map equivalent semantics around its enqueue/dequeue and split-WALT event ordering.
3. WALT accounting: Lisa's `walt_update_task_ravg` calls demand/busy/prediction updates in `kernel/sched/walt/walt.c`. Any package runtime accounting must preserve that order rather than copying flat-WALT line positions.
4. Cpuset: donor overrides inherited affinity for MIGT minor tasks. Lisa requires an exact semantic match in its cpuset fork/attach path; global affinity forcing is forbidden.
5. MIGT/Metis: this source map restores stock-era MIGT/package runtime only. It does not alias `/dev/migt` to `/dev/metis`.

## Developer Options cross-check discovered during manual execution

Working stock and Candidate0058 both report unlocked/orange boot state (`ro.boot.flash.locked=0`, `ro.boot.verifiedbootstate=orange`, lockstate unlocked), but only Candidate0058 has runtime debug/security divergence. Therefore unlocked bootloader state is not sufficient to explain the Developer Options regression.

Candidate0058 kernel command line contains `buildvariant=user` and no direct `force_debuggable` marker. The debug triplet still needs an early init/property source, and `ro.secure=0` needs a separately proven source.

## Next source-mutation gate

Do not create the first performance source patch until:
- the semantic hook audit passes on exact target and donor refs;
- the exact Android KABI reserve strategy for package runtime state is proven;
- task/user lifecycle hook locations are fixed in a generated patch plan.

Passing this audit does not mean Candidate0059 is ready for full CI.
