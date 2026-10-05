# MiYume reference review for Lisa - 2026-10-04

## Scope and decision

User reference: https://github.com/MiYume0721/android_kernel_xiaomi_sm8350_miyume
Pinned main: `6f0290557329655f29c9b1bc52eec33e36f859ba` (2026-10-02).
This is a research record, NOT a new kernel candidate or proof of device compatibility.
No BPF, F2FS, syscall, driver, security, toolchain or version change is applied by this commit.
Do not cancel/rebuild Candidate0057 for this documentation update.

The reference is useful as a feature/patch donor and a 5.4.302 comparison tree,
not a drop-in Lisa boot/kernel. Its README lists venus, mars, star and haydn,
not Lisa; the corresponding defconfigs and build targets are device-specific.
Makefile reports 5.4.302. README lists Clang/LLD18.1.8, BPF5.10 backport,
F2FS optimization, HyperOS4/Android17, and a warning that Android below15 has a
vendor error. These are maintainer statements, not our Lisa runtime validation.
A version label alone does not certify a complete upstream5.4.302 patch audit.

## Direct sources inspected

All reference paths below are pinned to the above commit unless a commit is named.

- README.md; Makefile lines1-25.
- arch/arm64/configs/venus_defconfig, including BPF/F2FS and mitigation options.
- kernel/bpf/Makefile and include/linux/bpf_types.h; ringbuf map declarations in
  include/uapi/linux/bpf.h and tools/include/uapi/linux/bpf.h.
- fs/f2fs/Kconfig and CONFIG_F2FS_CP_OPT references in xattr.c, file.c, inode.c,
  super.c, checkpoint.c, f2fs.h and include/trace/events/f2fs.h.
- Full changed-file diff for17e442827e48a1ea8b441956b7445fa9b6019c99.
- Full changed-file diff for2dd14248fd409a056943b8e029ecde3301266b2d.
- Diff for6a1672f6369b817494300f52ca088505d887dbae (venus power/suspend).
- Recent commit listing and targeted BPF/F2FS commit searches. The latter did
  not expose a complete individually replayable BPF5.10/F2FS backport series.
  Initial commit c8c95eb8c3ac10ed1f5b6624e4bdaa8c881612a4 imports the tree.
  Do not present a snapshot comparison as a fully audited upstream series.

Lisa source comparison uses the actual pinned build source
`6e568aabc77a06fa787baec1d9e60e4b559874a3`, not just main's packaging directory:
kernel/bpf/Makefile, fs/f2fs/Kconfig, include/uapi/asm-generic/unistd.h and
include/uapi/linux/capability.h. Relevant build scripts were checked for direct
BPF/F2FS replacement references; a complete all-files final-tree diff is not
claimed in this review.

Existing build config evidence was read directly from two previously retrieved
public Action artifacts:

| Artifact | ZIP SHA256 | Config |
|---|---|---|
| Candidate0056 artifact11283188386 | 0ad1b13b00f7324bf29890a3f5a5dc3486d29e82a5691cae5ea256e0aa2f667b | candidate-0056.config |
| Candidate0057 run37181431324 failure artifact11296320085 | 3a50c82aec889379f0efe4d24c3fe7aeccb2172b7e8f6374a8747350c6938679 | kernel/out/.config |

Both have BPF/BPF_SYSCALL/BPF_JIT/BPF_JIT_ALWAYS_ON/CGROUP_BPF/BPF_EVENTS=y,
NET_CLS_BPF=y and NETFILTER_XT_MATCH_BPF=y. BPF_STREAM_PARSER is disabled.
Both have F2FS_FS=y but F2FS_FS_COMPRESSION disabled; DEBUG_INFO_BTF disabled.
The0057 failure config is compile-time evidence, not a flashed-device result.

## A. BPF5.10 backport: real implementation differences, not another switch

MiYume's BPF Makefile includes ringbuf, bpf_iter/map_iter/task_iter/prog_iter,
trampoline, dispatcher, bpf_struct_ops and optional BPF LSM/local-storage paths.
BPF_MAP_TYPE_RINGBUF is wired in bpf_types.h and exposed in uapi headers.
The pinned Lisa baseline Makefile does not include these newer objects.
This supports a genuine newer-BPF source delta; it does not prove every5.10
helper/program type or arm64 JIT/trampoline path works, nor current security parity.

Potential value: newer userspace BPF loaders/features and richer event tracing.
Ring buffers can share storage across CPUs and preserve cross-CPU event ordering.
This is not a remedy for a WLAN module that never loaded due to duplicate HWID
exports; it must remain separate from current Wi-Fi module-ownership repair.

For an eventual port, inventory dependencies across kernel/bpf, net/core/filter.c,
net/bpf/attachment paths, include/linux and include/uapi/linux BPF/BTF headers,
arch/arm64/net/bpf_jit*, capabilities, LSM hooks and tools/testing/selftests/bpf.
Pair verifier, helper and JIT semantics; do not copy kernel/bpf alone or overwrite
shared vendor-facing structures without ABI/offset review. Keep CFI, MODVERSIONS,
SELinux enforcement and existing networking programs functional. Audit relevant
upstream fixes, not only the feature-introduction snapshot.

BTF parser support and a compiled vmlinux BTF section are different. Neither the
presence of btf.o nor 'BPF5.10' in README proves DEBUG_INFO_BTF is generated and
usable by a target tool. If requested, test BTF/CO-RE and pahole/toolchain separately.

Test gate proposal: target bpftool feature probes, selected BPF selftests,
Android BPF loader/netd startup, UID traffic accounting/firewall, VPN, tethering,
Wi-Fi power cycle/resume, and no new verifier/CFI errors. No such port or device
test was performed this turn.

References:
https://docs.kernel.org/5.10/bpf/index.html
https://docs.kernel.org/6.6/bpf/ringbuf.html

## B. F2FS: separate compression, fsync checkpoint policy, and locking

MiYume venus_defconfig enables:

```
CONFIG_F2FS_FS=y
CONFIG_F2FS_FS_COMPRESSION=y
CONFIG_F2FS_FS_LZO=y
CONFIG_F2FS_FS_LZORLE=y
CONFIG_F2FS_FS_LZ4=y
CONFIG_F2FS_FS_LZ4HC=y
CONFIG_F2FS_FS_ZSTD=y
CONFIG_F2FS_UNFAIR_RWSEM=y
CONFIG_F2FS_CP_OPT=y
```

The Lisa pinned source already defines F2FS compression with LZO/LZ4/ZSTD/LZO-RLE;
its measured0056/0057 configs do not enable it. Thus compression is not absent
source that needs wholesale import. MiYume adds a different combination including
LZ4HC, unfair rwsem and CP_OPT not declared in that Lisa Kconfig.

CP_OPT's stated goal is avoiding unnecessary fsync checkpoints for directory
xattr changes. It depends on F2FS_FS && QGKI && MACH_XIAOMI and changes inode
tracking and cleanup across several files. It is NOT equivalent to disabling
all checkpoints or adding one defconfig line. Unfair rwsem is a separate locking
policy whose tail latency/fairness must be measured under concurrent I/O.

Compiling compression support does not automatically compress existing/data
or convert ext4 toF2FS. Confirm the actual mount type, superblock feature flags,
fscrypt/inlinecrypto, recovery/fsck support and per-file policy before any write
feature changes. This review does not claim current live/data compression is
active or that filesystem-type/mount parameters were freshly captured.

Port sequence: correctness/security fixes first; optional compression support
without forced/data conversion; then an isolated CP_OPT experiment only after
journal/checkpoint/xattr/rename/fsync and recovery tests on disposable storage.
No nobarrier/fsync bypass, reformat or irreversible/data feature change merely
for a performance claim. Require measured improvement plus consistency tests;
no percentage/speedup is established by README or configuration alone.

Reference: https://docs.kernel.org/5.10/filesystems/f2fs.html

## C. Android17 compatibility: two concrete leads and important base differences

### 17e442827e48a1ea8b441956b7445fa9b6019c99: close_range and CLOEXEC

Maintainer reports Android17 bionic/netd helper spawning fails and hotspot turns
off without close_range+CLOSE_RANGE_CLOEXEC. Diff adds syscall436, fdtable support
and flags for arm64 and compat. It also removes their vendor process_madvise
entry at436 and changes SELinux capability mapping as part of the same commit.

Important: Lisa's pinned include/uapi/asm-generic/unistd.h already uses
process_madvise=440 and __NR_syscalls=441; close_range is not declared in the
inspected end-of-table region. MiYume's old436 collision is NOT Lisa's state.
Do not copy their table tail, shrink __NR_syscalls to437, or remove Lisa's440.
Any port must preserve current syscall behavior, add the correct436 entry,
review arm64 compat numbering and seccomp/userspace assumptions, and test
CLOEXEC and UNSHARE behavior, concurrency and old ROM regression separately.
Check original upstream278a5fbaed89 and6099733a459d as well as this adaptation.

The general bionic use of close_range predates Android17. AOSP commit
436980d31c99bdee3c794e26e662e885eba928d6 (2022) introduced use in posix_spawn,
and netd commit62b9020c4ef1c68c5d9bc3c46307595636daf3e8 (2024) uses
POSIX_SPAWN_CLOEXEC_DEFAULT for dnsmasq. The reference maintainer's specific
Android17 no-fallback explanation was not independently confirmed against the
exact ROM's bionic; the Android17 branch fetch failed. Attribute that causal
claim to the maintainer, not all Android17 devices or Lisa's present Wi-Fi fault.

### 2dd14248fd409a056943b8e029ecde3301266b2d: capability40

Maintainer reports a browser sandbox bounding-set probe rejected capability40,
and reports success after defining CAP_CHECKPOINT_RESTORE and CAP_LAST_CAP40.
The actual commit changes capability.h; SELinux classmap is changed in the
following close_range commit. Treat these as dependent changes, not standalone.

Lisa baseline has CAP_LAST_CAP=CAP_AUDIT_READ=37, whereas MiYume already had
CAP_PERFMON38/CAP_BPF39 before the40 change. A direct39-to40 patch is therefore
not equivalent. Review the semantics and SELinux capability2 names/permissions
for38/39/40, not just the highest integer. Adding a named capability and a
successful probe does not implement every privileged checkpoint/restore path.
Do not disable browser sandboxing or global SELinux enforcement to claim success.

HyperOS4/Android17 is a maintainer compatibility statement for their supported
hardware/ROM, not an official Lisa support guarantee. A kernel feature port does
not upgrade the Android system/vendor/framework or satisfy every HAL/VINTF
requirement. Current Lisa repairs stay on the existing ROM while this is studied.

Primary AOSP references:
https://android.googlesource.com/platform/bionic/+/436980d31c99bdee3c794e26e662e885eba928d6
https://android.googlesource.com/platform/system/netd.git/+/62b9020c4ef1c68c5d9bc3c46307595636daf3e8

## D. Additional useful lead, not today's WLAN load fix

6a1672f6369b817494300f52ca088505d887dbae includes Goodix regulator lifecycle,
NFC expected-freezer log handling, WLAN CE allocation retry and runtime-PM QoS.
The WLAN policy assumes a20000us threshold and discusses a measured QCA6490
resume path. Do not transfer that timing/device-specific power sequence to Lisa
without validating the actual chipset/driver/runtime PM path. These patches
operate after driver setup; they do not resolve duplicate-export module loading.
No directly established fix for Lisa's compressed transparent overlay corruption
or its PAS15 -22 was found in the reviewed commits. This is not an exhaustive
all-source defect review.

## E. Changes that must not be copied wholesale

Reference venus_defconfig has mitigations=off, several disabled mitigation flags,
KernelSU/SuSFS and UTS/bootconfig-spoof features, device-specific built-ins,
PANIC_ON_OOPS disabled and PANIC_TIMEOUT5. These differ from Lisa's established
protection/diagnostic and truthful-by-Tim0320 policy. BPF/F2FS/new-syscall work
must not silently import those settings, root/hiding facilities, DT/device drivers
or the other compiler version. Preserve original copyright/license/provenance
when selecting GPL source changes; author branding does not replace attribution.

## Prioritized integration plan

1. Complete current0057 build/checkpoint/independent verification and obtain
   actual WLAN/camera testing; keep battery/UFS/procfs/CFI and saved raw outputs.
2. In a separate research branch, inventory the5.4.302/common/vendor changes
   and the MiYume delta. Keep base upgrade and feature backports separable.
3. Prepare/test a dependency-complete BPF feature port and targeted Android
   syscall/capability compatibility patches only for an explicit target need.
4. Evaluate F2FS correctness first and optional performance features separately,
   with disposable-image tests and recovery compatibility before/data use.

Neither all three feature groups nor a ROM upgrade is authorized as an untested
replacement by this research note. No new boot is produced by this documentation.

## Current build snapshot observed during this review

Original build commit remains fa96c94a1ee076660c6c2ce80f967baa6a601820,
Run37183496384. Build steps through compile and immediate UNVERIFIED boot upload
passed; checkpoint construction was still running at the last read.
UNVERIFIED artifact11296217223, 65583619 compressed bytes, digest
91f2d20885fa55f0f0c2f77c0b767880d47b66502f55ee52cf1523cc446f46f6.
Source-review artifact11295723768 is not a boot. Independent verification had
not completed at that read. Re-read CI before reporting status. This milestone
confirms the new preservation stage ran; it is not permission to flash an
unverified image or proof of device stability.


## 2026-10-05 version-uplift history clarification

The initial MiYume repository import commit `c8c95eb8c3ac10ed1f5b6624e4bdaa8c881612a4` already reports:

`VERSION=5, PATCHLEVEL=4, SUBLEVEL=302`.

The current pinned donor `6f0290557329655f29c9b1bc52eec33e36f859ba` also reports 5.4.302.

Therefore this repository does **not** provide a clean, replayable 5.4.289 -> 5.4.302 stable-upgrade history. It remains valuable as a final-state Xiaomi/Qualcomm 5.4.302 comparison tree, especially for vendor conflict resolution, but official linux-stable v5.4.289..v5.4.302 must remain Candidate0061's upgrade source of truth.
