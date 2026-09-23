# Lisa Candidate 0009 — OS2.0.16 companion-state control

Status: **static gates PASS; device test blocked pending exact live rollback bytes**

## Provenance

Candidate 0009 is a controlled early-boot A/B package. It keeps the exact Candidate 0008 boot image unchanged and swaps the early companion partitions to the matching official OS2.0.16 values.

- Candidate 0008 boot SHA256:
  `585a69eae9ab0fe1ff028c5e9890c36e4d745778e9d60a9ebdc61649a81c2063`
- known-g598 kernel Image SHA256:
  `492b0b3910d1425cf434ec946851de73d40003f14adb29e695403bf5b60c2b55`
- matching OS2.0.16 vendor_boot SHA256:
  `c0a7528e8eacd2a86270ee017dfe90e657f1a0c5c40527869f89e915c2954a5a`
- matching OS2.0.16 dtbo SHA256:
  `db7c50147d8217c41cd86e53dda6e8ce93a5928a8f06ece8da92955a9c0e7ba7`

Build workflow:
- Run: `35897282074`
- Conclusion: `success`
- Artifact: `10766569520`
- Artifact name: `lisa-candidate-0009-os2-0-16-companion-control`
- Final gate: `LISA_CANDIDATE_0009_FINAL_GATE=PASS`

## Companion internal comparison

Workflow:
- Run: `35897331334`
- Conclusion: `success`
- Artifact: `10767815651`
- Artifact name: `lisa-os2-0-10-vs-os2-0-16-boot-chain-internals`
- Final gate: `LISA_COMPANION_INTERNAL_COMPARE=PASS`

Results:

```text
OS2.0.10 vendor_boot module count = 46
OS2.0.16 vendor_boot module count = 46
common module basenames          = 46
modules only in OS2.0.10         = 0
modules only in OS2.0.16         = 0
common modules changed SHA256    = 46
common modules changed vermagic  = 46

proxy-consumer.ko:
  OS2.0.10 = 5.4.289-g4c23b1a30923 SMP preempt mod_unload modversions aarch64
  OS2.0.16 = 5.4.289-g5987d69e25da SMP preempt mod_unload modversions aarch64

msm_drm.ko:
  OS2.0.10 = 5.4.289-qgki-g4c23b1a30923 SMP preempt mod_unload modversions aarch64
  OS2.0.16 = 5.4.289-qgki-g5987d69e25da SMP preempt mod_unload modversions aarch64

vendor_boot embedded DTB:
  OS2.0.10 SHA256 = 71a8c8dff3e31bdba49b376f851814b73d5ca49fde4a56befdc57b7fea4339d9
  OS2.0.16 SHA256 = 3e2c5c57da481dae32e9e7b46bdc760b20bdca56baa0882d4c404bbff1b99aef
  size both       = 4223378 bytes
  compatible      = qcom,lahaina
  model           = Qualcomm Technologies, Inc. Lahaina V2.1 SoC

DTBO:
  OS2.0.10 entries = 37
  OS2.0.16 entries = 37
  paired entries   = 37
  same entry SHA256 = 2
  same entry metadata = 37
```

Interpretation: the OS2.0.16 companion state is not a small one-module delta. The module set is structurally the same, but all 46 modules are rebuilt against the g598 lineage, the embedded vendor_boot DTB changes, and 35/37 DTBO payloads change. Therefore Candidate 0008 cannot be meaningfully judged against the current companion state without a controlled matching-companion A/B test.

## Current live-device rollback blocker

The exact current live device hashes previously measured are:

```text
live vendor_boot_a SHA256 =
6d2c626cc325058ba4c6f16a8f4043978404dfb5ce2f420d770f53d1f5d089f2

live dtbo_a SHA256 =
423828174f86a7aab8823fc1cf5347e9cc97f0f41c246c489bdf5793d79a922e
```

These are **not** the official OS2.0.10 OTA images:

```text
official OS2.0.10 vendor_boot =
9be4f2bcf3fcfe096c5d7d3d8adc36b59002750d51f1a437ec170e6afa908236

official OS2.0.10 dtbo =
d5a06c7aa1ee5b3aab5525e8984a980f0e52bdac4caad4fc14e554dd73556b5d
```

The previously uploaded standalone `vendor_boot.img` and `dtbo.img` were also checked and are the OS2.0.16 pair, not the current live rollback pair:

```text
uploaded vendor_boot.img =
c0a7528e8eacd2a86270ee017dfe90e657f1a0c5c40527869f89e915c2954a5a

uploaded dtbo.img =
db7c50147d8217c41cd86e53dda6e8ce93a5928a8f06ece8da92955a9c0e7ba7
```

Therefore the next device test must not be performed until exact byte-for-byte backups of the current live `vendor_boot_a` and `dtbo_a` are available and verified.

## Required device evidence

From TWRP / recovery with ADB root:

```powershell
adb shell "rm -f /tmp/vendor_boot_a_live.img /tmp/dtbo_a_live.img"
adb shell "dd if=/dev/block/by-name/vendor_boot_a of=/tmp/vendor_boot_a_live.img bs=4M"
adb shell "dd if=/dev/block/by-name/dtbo_a of=/tmp/dtbo_a_live.img bs=4M"

adb pull /tmp/vendor_boot_a_live.img .\vendor_boot_a_live.img
adb pull /tmp/dtbo_a_live.img .\dtbo_a_live.img

Get-FileHash .\vendor_boot_a_live.img -Algorithm SHA256
Get-FileHash .\dtbo_a_live.img -Algorithm SHA256
```

Expected hashes before Candidate 0009 device testing:

```text
vendor_boot_a_live.img =
6d2c626cc325058ba4c6f16a8f4043978404dfb5ce2f420d770f53d1f5d089f2

dtbo_a_live.img =
423828174f86a7aab8823fc1cf5347e9cc97f0f41c246c489bdf5793d79a922e
```

If either hash differs, stop and re-probe the current device state rather than using stale rollback assumptions.

## Decision gate

- Kernel mutation from Candidate 0008 failure: **not justified**
- Candidate 0009 static package: **PASS**
- Candidate 0009 device flash: **BLOCKED**
- First blocker: **exact current live vendor_boot_a / dtbo_a rollback bytes missing**
- Next action: obtain and verify those two live images, then perform the controlled Candidate 0009 companion-state A/B.
