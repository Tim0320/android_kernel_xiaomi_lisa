# Candidate0058: separate two-device failures and stage BPF ring-buffer backport

## Evidence scope (sanitized; no raw private logs or photographs published)

Both new captures identify the same flashed Candidate0057 package `fa96c94`.
Device A: Android14 system OS2.0.8.0.UKOMIXM, vendor OS2.0.8.0.UKOMIXM.
Device B: Android16 system OS3.0.304.0.WAFCNXM, vendor OS2.0.16.0.UKOCNXM.
The same kernel with different system/vendor packages is not a controlled
SIM-only comparison. A contains134894 logcat lines; B contains157087.
No captured kernel NULL/panic/raw-fault marker does not prove long-term health;
B's capture misses early kernel startup and direct dmesg access was denied.

The user confirms Wi-Fi connects and carries traffic on A. The supplied physical
screen photo clearly shows horizontal/tiled corruption in the floating dialog,
while the background settings list and keyboard remain readable. This confirms
the visual symptom, not a specific alpha/UBWC/fence bug. The earlier123958 HWC
capture showed DEVICE/SDE compressed transparent layers, but it was not captured
at the same moment as this photograph and must not be described as that frame.
Do not claim the next BPF patch repairs display composition.

## B: independently actionable userspace failures

B logcat lines37030-37045,15:05:54.920:

```
Process: com.android.phone
java.lang.NoSuchMethodError: No virtual method hasRemote()Z in
Lcom/xiaomi/continuity/networking/TrustedDeviceInfo;
... /product/app/LyraSdkApp/LyraSdkApp.apk
at com.android.services.telephony.relay.phonecall.PhoneContinuityController.updateRelayService
```

This is a definite framework/SDK Java interface mismatch and phone-process
crash. A kernel BPF backport cannot supply the missing Java method. Fixing it
requires a coherent system/product framework and continuity SDK from the ROM
maintainer, not renaming a kernel version, weakening SELinux or blindly swapping
an APK from another ROM. It is a plausible contributor to service instability,
not proof that it is the sole cause of2G-only registration.

Radio records show successful GSM/EDGE registration mixed with searching and
out-of-service states; no successful LTE/NR serving registration was identified
in this window. Modem-not-in-service events at15:06:15.406,15:06:35.823 and
15:06:54.650 are followed by failure to set state on the peripheral driver.
These events are not automatically proof of a complete modem firmware crash.
Coverage/carrier/SIM/allowed-radio settings and system-vendor-RIL compatibility
must be checked before blaming kernel transport alone.

B also has3502 `vendor.qti.hardware.perf@2.2-service: Unknown params` messages
and2734 `DisplayExtnImpl::SendContentFps: Content FPS Hint was not delivered!`
messages in the finite capture. This is a substantial failed-request/logging
loop, not a measured attribution of all lag. PowerInsight crashes separately
while trimming a missing design-capacity value, following failed charge-service
lookup/access. That is not proof that the physical battery or the restored
core battery driver has failed again.

A still has rmnet_ctl duplicate exports and a parallel5.4-gki fallback version
mismatch. B lacks the corresponding early kernel data; do not claim all A
module-loading observations were directly captured on B. Preserve the working
Wi-Fi and battery baseline while investigating cellular transport separately.

## BPF evidence and exact scope

A logcat lines6686-6687 says Android networking BPF programs loaded. At
15:04:02.171-172, lines64137-64156, MIUI monitoring fails to attach six programs
(scheduling/process/rss/fd monitoring) and cannot open its pinned ring-buffer
map (ENOENT). Missing pin paths do not alone prove unsupported kernel maps:
loader eligibility, object installation, helper/program support and permissions
also matter. The limited log has dropped bpfloader output. B does not provide
an equivalent complete early loader trace.

The user's BPF5.10 request is implemented here as an explicitly bounded first
stage, not a wholesale replacement or a claim of full5.10 feature parity:

- Canonical ring-buffer map type27 and helpers130-134: output/reserve/submit/
  discard/query, mmap and poll.
- Matched verifier reference/null/size/bounds handling, pointer spill/reload,
  helper-to-map and map-to-helper checks, base-only release, double-release and
  use-after-release rejection, pending-reservation protection and teardown
  irq_work synchronization.
- Preserve original helper IDs, shared bpf_map/bpf_map_ops/bpf_func_proto
  layouts, existing arm64 JIT, network/task structures, capabilities, CFI and
  MODVERSIONS. Initial ring-map creation remains CAP_SYS_ADMIN-gated.
- Ring-map freeze is explicitly unsupported. No array mmap, new iterator,
  trampoline, struct_ops, complete capability38-40, vmlinux BTF, F2FS,
  Android17 syscall or5.4.302 upgrade is claimed.

Sources are pinned baseline6e568aabc77a06fa787baec1d9e60e4b559874a3,
MiYume6f0290557329655f29c9b1bc52eec33e36f859ba, and upstream commits
457f44363a8894135c85b7a9afd2bd8196db24ab,
5b029a32cfe4600f5e10e36b41778506b90fd4de,
4e9077638301816a7d73fa1e1b4c1db4a7e3b59c. Original GPL provenance is retained.
Every affected source has before/after hashes in candidate_0058_bpf_sources.json.
The19-file expanded patch SHA256 is
`bc0bf3f5366b85d966f570a1dadcead2bbea6313c59de336cc1cada8b6df77e0`.
Four transport fragments concatenate to the pinned gzip, then expand to an
ordinary reviewable unified diff. They are not four independent kernel patches.

## Build and validation

Older recipes are unchanged. candidate_0058_factory.py checks exact0057 input
hashes and generates the eight versioned wrappers using the explicit recipe
patch, checking all output hashes before using them. The generated runtime
functions remain part of the independent checkpoint fingerprint. Only the
factory/verifier-only recipe patch is excluded because its concrete runtime
outputs are already checked. Generated wrappers and source patches are exported.

Local results before first hosted build:8 BPF integrity cases, exact baseline
patch/ABI-text/helper-ID roundtrip,10 identity tests,14 checkpoint tests,
11 flash-contract tests and inherited505 battery host inputs passed. C probe
host compilation and Python/YAML/embedded-shell syntax checks passed. These
are NOT target verifier execution or device results.

The independent verifier attempts a diskless ARM64 QEMU guest using the actual
compiled phone Image and a small static probe. Positive map/output/query/
spill/mmap/poll tests and negative reference/type/bounds tests must execute.
Failure to boot this board-oriented Image on generic virt is INCONCLUSIVE_BOOT,
not a BPF pass and not automatically a phone-kernel regression. Do not remove
a failed test or weaken kernel policy to fabricate a pass; inspect its logs and
repair the test environment or obtain an equivalent controlled target test.
The initial hosted build, QEMU test and device results are pending at commit time.

Keep the saved-before-verify pipeline: UNVERIFIED boot first, hashed reusable
checkpoint next, independent checks, then separately verified output. A pure
verifier/test fix uses the original58 checkpoint with source_run_id or an atomic
candidate_0058_reverify_request.json update; preserve original build identity
and boot bytes. Actual BPF source changes require a new build. User-facing
version is5.4.289-qgki-lisa-c0058-r<package_sha7>-by-Tim0320.

No physical phone flashing, system/vendor APK changes, modem/persist/calibration,
thermal, GPU parameter or battery algorithm changes are performed by this build.
Follow the same hourly Lisa task; observe still checks2/2/5 minutes. The source
reviews37185289887 and37185716411 are successful read-only audits, not boot runs.
Read current Actions for the actual next-candidate commit/run/status.
