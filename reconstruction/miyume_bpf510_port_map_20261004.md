# MiYume Linux 5.10 BPF backport map for Lisa

Reference repository:
- MiYume0721/android_kernel_xiaomi_sm8350_miyume
- pinned working tree: 6f0290557329655f29c9b1bc52eec33e36f859ba
- initial repository commit containing the BPF stack: c8c95eb8c3ac
- Lisa reconstruction baseline: 6e568aabc77a06fa787baec1d9e60e4b559874a3
- upstream comparison target: Linux v5.10

## Important history result

The MiYume repository does not expose the Linux-5.10 BPF work as a clean
series of later commits. ringbuf.c, verifier.c, trampoline.c, bpf_iter.c and
bpf_struct_ops.c all trace to the initial repository commit c8c95eb8c3ac.
Therefore there is no trustworthy single `git cherry-pick <BPF commit>`
sequence from that repository.

The safe Lisa workflow is to reconstruct a feature/dependency patch series
from the MiYume tree, compare each slice with upstream v5.10 and the Lisa
5.4.289 baseline, and preserve Qualcomm/Android-specific ABI and security
policy. Do not replace kernel/bpf wholesale.

MiYume's kernel/bpf/Makefile structurally follows the v5.10 layout: iterator
objects, ringbuf, trampoline, dispatcher, bpf_struct_ops, local storage and
net namespace are built in the same functional groups. It also carries
additional vendor/newer material (for example FUSE-BPF), and key core files
such as syscall.c/verifier.c/core.c are not byte-identical to upstream v5.10.
This is a successful reference implementation, not a byte-copy target.

## Port groups / exact update locations

### Stage A - Ring buffer (already staged in Candidate0058)

New/changed core locations:
- include/uapi/linux/bpf.h
- include/linux/bpf.h
- include/linux/bpf_types.h
- include/linux/bpf_verifier.h
- kernel/bpf/Makefile
- kernel/bpf/ringbuf.c (new versus Lisa baseline)
- kernel/bpf/helpers.c
- kernel/bpf/syscall.c
- kernel/bpf/verifier.c
- kernel/bpf/core.c as required by verifier/reference semantics

Required user ABI concepts:
- BPF_MAP_TYPE_RINGBUF
- BPF_FUNC_ringbuf_output/reserve/submit/discard/query
- mmap + poll handling
- verifier reference tracking and bounds

Candidate0058 e476b67 already implements an explicitly limited version of this
stage and preserves the existing shared-structure ABI/CFI/MODVERSIONS policy.
Its generic ARM64 QEMU runtime test is currently INCONCLUSIVE_BOOT; do not
call it a target-runtime pass.

### Stage B - Iterator/link infrastructure

MiYume files absent from the Lisa baseline:
- kernel/bpf/bpf_iter.c
- kernel/bpf/map_iter.c
- kernel/bpf/task_iter.c
- kernel/bpf/prog_iter.c

Supporting changes are required in:
- kernel/bpf/Makefile
- kernel/bpf/syscall.c
- kernel/bpf/btf.c
- kernel/bpf/inode.c
- kernel/bpf/hashtab.c
- kernel/bpf/arraymap.c
- include/uapi/linux/bpf.h
- include/linux/bpf.h
- include/linux/bpf_types.h
- include/linux/bpf_verifier.h

API/features to map:
- BPF_LINK_TYPE_ITER
- BPF_ITER_CREATE
- iterator link lifetime/refcount behavior
- map/task/program iterator registration
- BTF dependencies

Do not enable this stage before its BTF/link/refcount dependencies are
verified on the Lisa baseline.

### Stage C - Trampoline / tracing / extension programs

MiYume files absent from Lisa:
- kernel/bpf/trampoline.c
- kernel/bpf/dispatcher.c

Major supporting files:
- kernel/bpf/core.c
- kernel/bpf/syscall.c
- kernel/bpf/verifier.c
- kernel/bpf/btf.c
- include/linux/bpf.h
- include/linux/bpf_verifier.h
- include/linux/bpf_types.h
- include/uapi/linux/bpf.h
- arch/arm64/net/bpf_jit_comp.c

Relevant program/link concepts include tracing/extension programs and
trampoline lifetime/dispatch behavior. ARM64 JIT compatibility must be tested
instead of assuming the MiYume implementation is drop-in.

### Stage D - struct_ops

MiYume files absent from Lisa:
- kernel/bpf/bpf_struct_ops.c
- kernel/bpf/bpf_struct_ops_types.h

Supporting changes:
- kernel/bpf/Makefile
- kernel/bpf/btf.c
- kernel/bpf/syscall.c
- kernel/bpf/verifier.c
- include/linux/bpf.h
- include/linux/bpf_types.h
- include/linux/bpf_verifier.h
- include/uapi/linux/bpf.h

Relevant ABI:
- BPF_PROG_TYPE_STRUCT_OPS
- BPF_MAP_TYPE_STRUCT_OPS

This stage depends heavily on BTF and type validation; do not implement it by
only adding enum values or Makefile objects.

### Stage E - newer local-storage / namespace / optional BPF integration

MiYume has additional source units absent from the Lisa baseline:
- kernel/bpf/bpf_local_storage.c
- kernel/bpf/net_namespace.c
- kernel/bpf/bpf_inode_storage.c
- kernel/bpf/bpf_lsm.c
- include/linux/bpf-netns.h
- include/linux/bpf_local_storage.h
- include/linux/bpf_lsm.h

Related integration points include:
- kernel/bpf/syscall.c
- kernel/bpf/btf.c
- kernel/bpf/hashtab.c
- kernel/bpf/arraymap.c
- net/core/filter.c
- include/linux/bpf*.h
- include/uapi/linux/bpf.h

These are separate capabilities. They should not all be forced on merely
because MiYume builds them under certain configs.

### Stage F - tools, BTF, preload and selftests

MiYume includes a much larger tools/testing/selftests/bpf tree plus:
- kernel/bpf/preload/
- kernel/bpf/preload/iterators/
- kernel/bpf/sysfs_btf.c
- tools/include/uapi/linux/bpf.h

Use the relevant tests as acceptance criteria, but do not require every host
tool/preload feature in the phone kernel. Lisa currently has DEBUG_INFO_BTF
disabled, so CO-RE/BTF-dependent features need a deliberate toolchain and
image-size plan.

## Key structural differences already confirmed

Lisa baseline Makefile lacks:
- bpf_iter.o/map_iter.o/task_iter.o/prog_iter.o
- ringbuf.o
- trampoline.o
- dispatcher.o
- bpf_struct_ops.o
- bpf_local_storage.o
- net_namespace.o

MiYume's include/linux/bpf_types.h additionally registers tracing, struct_ops,
extension, iterator links, ringbuf and other newer map/program/link types.
Lisa's baseline bpf_types.h is the older two-argument BPF_PROG_TYPE model and
does not contain these groups. Therefore a whole-file copy would change shared
type plumbing and can silently break Qualcomm/Android call sites.

MiYume contains 437 paths in the inspected BPF/selftest/include/JIT scope
whereas the Lisa baseline tree exposes 40 paths under the same broad filter.
The 437 count includes tests and supporting files and must NOT be interpreted
as 397 mandatory kernel patches.

## Relationship to user-B jank work

User-B performance compatibility remains the runtime repair priority. The new
BPF work is allowed to proceed in parallel as source/provenance/dependency
mapping, but additional runtime BPF stages must not displace the current
Metis/TurboSched/perf/task-profile investigation.

Current B observations include repeated /dev/metis open failures while
TurboSched v2/core-app/top20 features are enabled, failed FPS hints and
schedtune profile warnings. There is no evidence that the remaining MiYume BPF
stages will directly fix those symptoms. Keep the two workstreams separate.

## Recommended integration order after jank stabilization

1. Finish/validate Stage A ringbuf on an equivalent target execution path.
2. Iterator/link infrastructure.
3. Trampoline/dispatcher + ARM64 JIT tests.
4. struct_ops + required BTF subset.
5. Optional local storage/netns/LSM features only when Android/MIUI consumers
   actually require them.
6. BTF/CO-RE/preload and larger selftest expansion.
7. Only then describe the Lisa kernel as having the intended 5.10 BPF feature
   set; do not label the ringbuf-only stage as complete BPF5.10 parity.

Every stage must preserve existing Lisa battery/UFS/Wi-Fi ownership fixes,
CFI, MODVERSIONS and kernel identity. Source-level changes require a new build;
verifier/test-only fixes reuse the saved checkpoint when recipe fingerprint
permits.
