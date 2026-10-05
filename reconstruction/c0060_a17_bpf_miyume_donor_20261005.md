# Candidate0060 Android 17 / HyperOS 4 BPF donor preparation

Prepared: 2026-10-05

## Donor pinned for source comparison

Primary donor:
- Repository: MiYume0721/android_kernel_xiaomi_sm8350_miyume
- Pinned source commit: 6f0290557329655f29c9b1bc52eec33e36f859ba
- Kernel version: 5.4.302
- README claim: Linux 5.10 BPF backport and HyperOS 4.0 / Android 17 support
- SoC family: SM8350/lahaina. The BPF core is useful as a generic 5.4 donor; device drivers are NOT to be copied to Lisa.

Android 17 compatibility commits worth auditing separately:
- 17e442827e48a1ea8b441956b7445fa9b6019c99
  - backports close_range() and CLOSE_RANGE_CLOEXEC at syscall 436 for Android 17 bionic/netd compatibility.
- 2dd14248fd409a056943b8e029ecde3301266b2d
  - adds CAP_CHECKPOINT_RESTORE=40 and updates CAP_LAST_CAP / SELinux capability class map.

## BPF surface present in donor

The donor kernel/bpf tree contains, among others:
- ringbuf.c
- btf.c
- bpf_iter.c
- map_iter.c
- task_iter.c
- prog_iter.c
- trampoline.c
- bpf_struct_ops.c
- bpf_lsm.c
- bpf_local_storage.c
- bpf_inode_storage.c
- syscall.c
- verifier.c
- helpers.c
- cgroup.c
- dispatcher.c

The donor UAPI includes newer commands used by the 5.10-era BPF ABI:
- BPF_LINK_CREATE
- BPF_LINK_UPDATE
- BPF_LINK_GET_FD_BY_ID
- BPF_LINK_GET_NEXT_ID
- BPF_ENABLE_STATS
- BPF_ITER_CREATE
- BPF_LINK_DETACH
- BPF_PROG_BIND_MAP

Relevant map types include:
- BPF_MAP_TYPE_STRUCT_OPS
- BPF_MAP_TYPE_RINGBUF
- BPF_MAP_TYPE_INODE_STORAGE

Relevant program types include:
- BPF_PROG_TYPE_TRACING
- BPF_PROG_TYPE_STRUCT_OPS
- BPF_PROG_TYPE_EXT
- BPF_PROG_TYPE_LSM
- BPF_PROG_TYPE_SK_LOOKUP
- BPF_PROG_TYPE_FUSE

Relevant attach types include:
- BPF_TRACE_FENTRY
- BPF_TRACE_FEXIT
- BPF_MODIFY_RETURN
- BPF_LSM_MAC
- BPF_TRACE_ITER
- BPF_CGROUP_INET_SOCK_RELEASE
- BPF_SK_LOOKUP

## Candidate0059 gap

Candidate0059 currently has the audited Stage-A ring-buffer subset:
- BPF ringbuf map type
- helpers output/reserve/submit/discard/query
- mmap/poll support
- verifier adaptations for that subset
- linked ringbuf/verifier objects

Candidate0059 explicitly does NOT claim full Linux 5.10 BPF parity.

Therefore Candidate0060 must begin with an exact source/API gap report instead of blindly copying kernel/bpf.

## Candidate0060 revised port order

Candidate0060 is now a compatibility-overlay specification, not the version-uplift base.

1. Freeze Candidate0059 as the known 5.4.289 static/device comparison parent.
2. Complete Candidate0061 first: semantically uplift the Lisa vendor tree from official Linux 5.4.289 to official Linux 5.4.302 while preserving Candidate0059 gates.
3. Use that Lisa 5.4.302 result as the source base for Candidate0060 BPF/A17 compatibility work.
4. Compare MiYume 5.4.302 against official Linux v5.4.302 and extract only donor-specific BPF/Android17 deltas. This avoids conflating the 5.4.289->5.4.302 stable delta with BPF5.10 feature work.
5. Backport only the BPF dependencies actually required by Android 17 / HyperOS 4 userspace.
6. Audit the non-BPF Android 17 ABI requirements:
   - close_range + CLOSE_RANGE_CLOEXEC
   - CAP_PERFMON=38 / CAP_BPF=39 / CAP_CHECKPOINT_RESTORE=40 and matching SELinux capability2 semantics
7. Preserve Lisa QGKI ABI, CFI, MODVERSIONS and existing module ownership.
8. Compile and require real linked-symbol/object gates.
9. Device-test bpfloader/netd and capture the first unsupported map/helper/prog/link operation.

Why the order changed:
- MiYume is itself based on 5.4.302.
- Official 5.4.289->5.4.302 does not add the desired Linux5.10 BPF surface; the core BPF files checked (Makefile, btf.c, syscall.c, verifier.c, helpers.c, uapi bpf.h) are byte-identical between official 5.4.289 and 5.4.302.
- Some shared dependencies do change during the stable uplift, e.g. net/core/filter.c and fs/file.c. Applying A17/BPF work before the uplift would create avoidable three-way conflict/retest work.
- Therefore the clean extraction boundary is official-v5.4.302 -> MiYume-v5.4.302, applied onto Lisa-v5.4.302.

Developer Options remains a separate runtime/property provenance track. Its repair must not be represented as part of the 5.4.302 stable uplift or BPF backport.

## Hard exclusions

Do NOT import these donor changes merely because they are present in the same repository:
- SELinux permissive support
- androidboot.selinux bypass/hacks
- KernelSU/ReSukiSU/SuSFS
- F2FS tuning
- device-specific SM8350 drivers/DTS
- global frequency pinning or thermal bypass
- wholesale 5.4.302 version uplift

Known donor commits related to SELinux permissive/debug behavior must remain excluded, including:
- 46f1063d8a6f88fe8ea627bc7554834d9a614a0f
- e277edef54e55a7604bf8f3add1832dc518f6171

## Acceptance

A Candidate0060 BPF stage is accepted only when:
- source provenance is pinned,
- every changed file is inventoried,
- Lisa config dependencies are explicit,
- vmlinux/System.map proves linkage,
- module ABI gates remain clean,
- bpfloader/netd device logs do not show the targeted missing ABI,
- no SELinux weakening or fake success path is introduced.
