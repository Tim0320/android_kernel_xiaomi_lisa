# Lisa device-test history

This file records real-device boot-test iterations for reconstructed Lisa kernel/boot images. It is intended to remain append-only so later failures can be compared with earlier candidates.

## Iteration 0001 — 2026-09-23 17:52 +08:00

- Candidate: reconstructed `boot.img`
- Boot SHA256: `82697e2df7368c17d8d3ffd54947ff0213c6ed80f47edf5fb17475093b760a07`
- Boot size: `201326592` bytes
- Device: Xiaomi 11 Lite 5G NE (`lisa`)
- Slot observed in TWRP: `_a`
- TWRP: `3.7.1_12-1_Rocky7842`
- User-observed outcome: `black-screen-reboot`
- Note: `閃一屏`
- Collector: `collect_lisa_twrp_logs.ps1 v1.0.2`
- Uploaded package SHA256: `e44326ce7c1f0d38b172ca221979a4285b12219a1657fcd74198e0223eb23b85`
- Internal `SHA256SUMS.txt`: all packaged files verified successfully.

### Evidence

The recovery-side `/sys/fs/pstore` directory exists but contains no records. `/proc/last_kmsg` is unavailable and `/data/vendor/ramoops` is absent, so this package does not contain the failed Android kernel's crash trace.

The TWRP command line exposes the device-specific persistent log path:

```text
block2mtd.block2mtd=/dev/block/sda17,2097152
mtdoops.mtddev=0
mtdoops.record_size=2097152
mtdoops.dump_oops=0
printk.always_kmsg_dump=1
```

TWRP's block-device listing maps:

```text
oops -> /dev/block/sda17
```

Therefore the highest-priority missing evidence for this iteration is a raw copy of `/dev/block/by-name/oops` (same backing device: `/dev/block/sda17`).

Recovery reports AVB state `orange` and `vbmeta.device_state=unlocked`. The ordinary `ro.boot.bootreason` and `sys.boot.reason` properties are empty. The recovery command line contains `bootinfo.pureason=0x80001` and `bootinfo.pdreason=0x80`; these are retained as evidence but are not treated here as proof of a kernel panic.

### Collector observations

Collector v1.0.2 has three follow-up issues:

1. `pstore_present=true` currently means only that the path exists; it does not mean crash records exist.
2. Successful `adb pull` operations can be logged as `ERROR` because Windows PowerShell surfaces adb progress written to stderr as an error record even when the file was pulled successfully.
3. The collector does not yet copy the Lisa-specific `oops` block partition, which is the most important persistent log source on this device.

### Next evidence

While still in TWRP, capture the raw `oops` partition and record its SHA256 before another boot attempt can overwrite it.


### Iteration 0001 follow-up: raw oops partition

Uploaded raw partition: `lisa_oops_iter0001.bin`

- Size: `16777216` bytes
- SHA256: `a78f91d0262e9b37823ee5060fdf5b4a3dd0b34614769149fc428a2a81ac6de2`
- Layout observed: eight 2 MiB mtdoops slots.
- Readable slot indices: `1293` through `1300`.
- Highest index: `1300`, carrying an older `5.4.289-qgki-g5987d69e25da` record.
- Slots carrying `5.4.289-qgki-g4c23b1a30923` are older indices (approximately `1293`-`1297`) and therefore cannot be treated as the just-tested boot.
- Conclusion: the failed reconstructed boot did not commit a new mtdoops record before reset. Do not use the stale g4c23 slot tail as the current crash root cause.

The TWRP filesystem listing shows `/cache/recovery/last_kmsg` and rotated `last_kmsg.*` files, and the GPT exposes a `logdump` partition. These are the next evidence sources to collect before changing the kernel.


### Iteration 0001 follow-up: cache recovery history and logdump

Additional evidence:

- `lisa_last_kmsg_iter0001.txt`: 213623 bytes, SHA256 `325d8781b2f55e029e11ff32d8e8f8581e262b3f772002de85c507c7c81ebdf8`.
- `lisa_last_kmsg_iter0001_prev.txt`: 215564 bytes, SHA256 `bc0425962f7ec5edd84d2a21c9932b6b93994c513781f9e1a1b51e56f0c69f88`.
- `lisa_logdump_iter0001.bin`: 67108864 bytes, SHA256 `3b6a07d0d404fab4e23b6d34bc6696a6a312dd92821332385e5af7c01c421351`.

Both cache last_kmsg files are complete TWRP/recovery Linux 5.4.210 boots, not the failed reconstructed 5.4.289 boot. Their repeated dev_pm_attach_wake_irq warning is followed by continued recovery initialization and therefore is not treated as the current boot blocker.

The 64 MiB logdump image is entirely zero-filled and contains no crash payload.

Together with the stale mtdoops-ring result, Iteration 0001 still lacks a trustworthy crash trace from the newly tested reconstructed kernel. No kernel source change is justified from these records alone.

Collector v1.1.0 now automatically captures oops, logdump, all cache/recovery last_kmsg* and last_log* history, and inventories minidump/rawdump/logfs/mdcompress partition sizes.


## Iteration 0002 — 2026-09-23 20:51 +08:00

- Candidate: reconstructed `boot.img`
- Boot SHA256: `82697e2df7368c17d8d3ffd54947ff0213c6ed80f47edf5fb17475093b760a07`
- Boot size: `201326592` bytes
- Device: Xiaomi 11 Lite 5G NE (`lisa`)
- Slot: `_a`
- TWRP: `3.7.1_12-1_Rocky7842`
- Outcome: `black-screen-reboot`
- Note: `閃一屏`
- Collector: `collect_lisa_twrp_logs.ps1 v1.1.0`
- Package SHA256: `a757878e1f7fecce3b299ce7f200db06b7f1f3918788446265e292d1f45b744d`
- Package integrity: all 55 listed files matched `SHA256SUMS.txt`.

### Evidence

The `oops` partition is byte-for-byte identical to iteration 0001:

```text
size=16777216
sha256=a78f91d0262e9b37823ee5060fdf5b4a3dd0b34614769149fc428a2a81ac6de2
```

Therefore no new mtdoops record was committed by the failed reconstructed boot.

The `logdump` partition is 64 MiB with SHA256 `08cf91fa91ba50db1e55bb54fa1d7efda2cee491c97e2f7fd7f1160d2d825f9a`. Only the first 29 bytes are non-zero and contain the ASCII marker `/dev/block/by-name/logdump -\n`; all remaining bytes are zero. This is not a usable crash payload.

All 11 collected `/cache/recovery/last_kmsg*` files are recovery-kernel histories. They report Linux versions `5.4.210-qgki-*` or `5.4.86-qgki-*`, not the tested reconstructed `5.4.289-qgki-g4c23b1a30923`. They cannot identify the current failure root cause.

Recovery cmdline after the failed boot reports:

```text
bootinfo.pureason=0x80011
bootinfo.pdreason=0x2
androidboot.ramdump=disable
```

These values are retained as reboot-context evidence only; they are not treated as standalone proof of kernel panic.

The dump partition inventory shows:

```text
oops      16777216
logdump   67108864
minidump  100663296
rawdump   209715200
logfs     8388608
mdcompress 20971520
```

### Decision

Evidence remains insufficient for a safe kernel source change. The next test must collect `minidump`, `mdcompress`, and `logfs`. `rawdump` is intentionally opt-in because it is 200 MiB and may contain RAM-resident sensitive data.

Collector v1.2.0 adds automatic capture for those smaller diagnostic partitions, records non-zero-byte statistics for raw dumps, records `pureason/pdreason`, and keeps `rawdump` behind `-IncludeRawDump`.


## Iteration 0003 — 2026-09-23 21:10 +08:00

- Candidate: reconstructed `boot.img`
- Boot SHA256: `82697e2df7368c17d8d3ffd54947ff0213c6ed80f47edf5fb17475093b760a07`
- Boot size: `201326592` bytes
- Device: Xiaomi 11 Lite 5G NE (`lisa`)
- Slot: `_a`
- TWRP: `3.7.1_12-1_Rocky7842`
- Outcome: `black-screen-reboot`
- Note: `閃一屏`
- Collector: `collect_lisa_twrp_logs.ps1 v1.2.0`

### Dump partition results

```text
oops:
  size=16777216
  sha256=a78f91d0262e9b37823ee5060fdf5b4a3dd0b34614769149fc428a2a81ac6de2
  unchanged from iterations 0001/0002

logdump:
  size=67108864
  sha256=08cf91fa91ba50db1e55bb54fa1d7efda2cee491c97e2f7fd7f1160d2d825f9a
  nonzero_bytes=29
  not a usable crash payload

minidump:
  size=100663296
  sha256=40bdc781b7e2a2ff8c52e50f9ad713168012b796d60adc8650b32eab2f48ea6d
  nonzero_bytes=36511917

mdcompress:
  size=20971520
  sha256=072ce52ce7afcf65859e21f3b11e5df8122690e8ee7863d001aabc99d90a25ea
  nonzero_bytes=32
  effectively empty

logfs:
  size=8388608
  sha256=2767ec897ec4db8df5b2c8adc5e8f95e94f431408502254a5a41ef0d4c3328bb
  FAT12 filesystem containing UefiLog0.txt through UefiLog4.txt
```

### Minidump finding

The minidump contains historical kernel logs and panic records, including a fatal exception in `qcom_icc_set_qos -> regmap_mmio_read32le`, but the associated Linux release is `5.4.289-qgki-g5987d69e25da`, not the tested reconstructed `5.4.289-qgki-g4c23b1a30923`.

The complete minidump contains no `g4c23` / `4c23b1a30923` release marker. Therefore the historical panic must not be attributed to iteration 0003.

### UEFI / logfs finding

The rotating UEFI logs show mission-mode boots of slot `_a` that load the modified `boot_a`, report the expected AVB hash mismatch while the unlocked device remains in orange state, and then continue through:

```text
VB2: Authenticate complete! boot state is: orange
...
Shutting Down UEFI Boot Services
Start EBS
```

The retry count decreases between repeated mission boots. This demonstrates that the bootloader is handing control to the kernel rather than rejecting the candidate boot image.

The newest fastboot/recovery session reports `pureason=0x80011`, `pdreason=0x2`. These remain context only.

### Decision

The blocker is now narrowed to after UEFI ExitBootServices / kernel handoff but before the reconstructed kernel leaves a reliable current-version persistent crash record.

No kernel source change is made from the stale `g5987` minidump panic.

The next required evidence is the 200 MiB `rawdump` partition from the same failed-boot state, collected before another boot attempt. If it also lacks the `g4c23` kernel marker, the failure is likely occurring before current-kernel dump capture becomes usable and a different early-boot instrumentation strategy will be required.


## Iteration 0004 — 2026-09-23 21:18 +08:00

- Candidate: reconstructed `boot.img`
- Boot SHA256: `82697e2df7368c17d8d3ffd54947ff0213c6ed80f47edf5fb17475093b760a07`
- Outcome: `black-screen-reboot`
- Collector: `collect_lisa_twrp_logs.ps1 v1.2.0`
- Package bytes: `14057078`
- Package SHA256: `6f38bba2b219f96d957f83dec6e3a009b80d0f3a6d69cad08c5890fcf5025d65`

### rawdump verification

The small ZIP size is expected compression, not a truncated rawdump.

```text
rawdump logical size = 209715200 bytes
rawdump SHA256 = 605b2027582ca8c4b3c4d1e04d09ecc7b612dc9fe4ca97208c57bc2e3355710c
nonzero_bytes = 10954478
first_nonzero_offset = 0
last_nonzero_offset = 67936879
compressed size inside ZIP ~= 1.46 MiB
```

The complete rawdump contains no `g4c23b1a30923`, `5.4.289-qgki-g4c23`, or `4c23b1a30923` marker.

All Linux 5.4.289 release strings found in rawdump identify the historical `5.4.289-qgki-g5987d69e25da` kernel. The panic records are likewise the stale `qcom_icc_set_qos -> regmap_mmio_read32le` failure from that older kernel.

Therefore iteration 0004 confirms that the currently tested g4c23 candidate resets before it leaves an identifiable current-kernel persistent dump record.

### Next diagnostic action

Run the existing ARM64 early-boot binary comparison against the exact current validated/repacked candidate artifact (`10736688529`) rather than the stale artifact previously referenced by the workflow. Compare the stock OS2.0.10 Image against the exact reconstructed Image header, entry instructions, text offset, declared image size, flags, reserved fields, appended payloads, and embedded config.


## Candidate 0005 — exact OS2.0.10 baseline repack, awaiting device test

- Generated by workflow run: `35870049702`
- Artifact ID: `10755230538`
- Artifact name: `lisa-qgki-reconstructed-boot-img-v3-exact-os2-0-10`
- Boot SHA256: `313ad67bd53d379ec98de5e65b732c16783a2280c57a981f81655082bfe29c77`
- Boot size: `201326592` bytes
- Rebuilt Image SHA256: `617c015a74e86b9a98479b6f4c657335484aa6351723cd41615e9f717226afb2`
- Target release: `5.4.289-qgki-g4c23b1a30923`
- Exact OS2.0.10 stock boot SHA256: `0959eaa1bc914d570792b53207fc9f481b3986c8b9f2a0ec2a76a1fd625a3c1f`
- Exact OS2.0.10 stock Image SHA256: `2162041efe1e4ac3e86bd934d4ccd9a4e00c5cd80e23c8085dfd0e0995430166`

### Validation status

The exact-baseline repack workflow completed successfully. All static gates passed:

```text
EXACT_BASELINE_ARM64_HEADER_GATE=PASS
LISA_EXACT_OS2_0_10_REPACK_GATE=PASS
```

The reconstructed Image matches the stock ARM64 hard fields used by the gate: `text_offset`, `flags`, `res2`, `res3`, `res4`, ARM64 magic, and `res5`. The target release is present. The exact stock OS2.0.10 ramdisk is preserved byte-for-byte, boot header v3 metadata is preserved except for kernel size, the kernel payload hash is exact, partition size is preserved, the unused tail is zeroed, and no stale AVB footer is copied.

The rebuilt Image also passed the existing ABI/runtime evidence gates: six-symbol CRC compatibility, `msm_drm` 736/736 compatibility with zero mismatches/missing symbols, and the final runtime-layout gate.

### Required next evidence

No further kernel/source mutation is justified before a real-device boot test of this exact candidate. Flash/test **Candidate 0005** and record the observed outcome. If it still fails, collect a fresh TWRP evidence bundle tied specifically to boot SHA256 `313ad67bd53d379ec98de5e65b732c16783a2280c57a981f81655082bfe29c77` before making another kernel change.


## Iteration 0005 — 2026-09-23 22:19 +08:00

- Candidate: exact OS2.0.10 baseline repack (Candidate 0005)
- Generated by workflow run: `35870049702`
- Artifact ID: `10755230538`
- Boot SHA256: `313ad67bd53d379ec98de5e65b732c16783a2280c57a981f81655082bfe29c77`
- Boot size: `201326592` bytes
- Device: Xiaomi 11 Lite 5G NE (`lisa`)
- Slot: `_a`
- TWRP: `3.7.1_12-1_Rocky7842`
- Outcome: `black-screen-reboot`
- Note: `閃一屏`
- Collector: `collect_lisa_twrp_logs.ps1 v1.2.0`
- Evidence package SHA256: `1ca9d28acf7be8983675f5554c1e24865702c8591634bfda49b12c1cca6a9d83`
- Evidence package bytes: `12599508`

### Persistent dump comparison

The dump partitions that would normally carry a current kernel crash did **not** change from the pre-Candidate-0005 evidence:

```text
oops:
  sha256=a78f91d0262e9b37823ee5060fdf5b4a3dd0b34614769149fc428a2a81ac6de2
  bytes=16777216
  exact same partition hash as Iterations 0001/0002 and therefore stale

logdump:
  sha256=08cf91fa91ba50db1e55bb54fa1d7efda2cee491c97e2f7fd7f1160d2d825f9a
  bytes=67108864
  nonzero_bytes=29
  still only the partition-name marker

minidump:
  sha256=40bdc781b7e2a2ff8c52e50f9ad713168012b796d60adc8650b32eab2f48ea6d
  bytes=100663296
  nonzero_bytes=36511917
  exact same hash as Iteration 0003; historical payload, not Candidate 0005

mdcompress:
  sha256=072ce52ce7afcf65859e21f3b11e5df8122690e8ee7863d001aabc99d90a25ea
  bytes=20971520
  nonzero_bytes=32
  effectively empty
```

The unchanged `oops` hash is especially important. It contains old `g4c23`, `g5987`, `magiskinit`, and `system_b` mount-failure records, but because the entire partition is byte-for-byte unchanged from evidence collected before Candidate 0005, none of those records may be attributed to the current boot attempt.

### Fresh UEFI evidence

`logfs` did change:

```text
logfs_sha256=b5c9784dd1ee8caabc190b74abcfdfbf85665a6cf42e4536df186d72806371c1
logfs_bytes=8388608
```

The newest mission-mode page records:

```text
KeyPress:0, BootReason:34
Fastboot=0, Recovery:0
avb_slot_verify: boot_a hash mismatch
VB2: Authenticate complete! boot state is: orange
fatal error is not set
Hyp version: 1
Shutting Down UEFI Boot Services: 4357 ms
Start EBS [4357]
```

This is fresh evidence that the unlocked bootloader accepts the modified `boot_a`, continues in orange state, and reaches ExitBootServices / kernel handoff. Candidate 0005 then resets before it creates a new mtdoops/minidump/mdcompress record.

### Decision

Candidate 0005 proves that replacing the old OS2.0.16 ramdisk baseline with the exact OS2.0.10 ramdisk/header was necessary for correctness but was not sufficient to make the reconstructed Image boot.

The first current blocker is now constrained to the **very early kernel handoff window after UEFI ExitBootServices and before persistent kernel logging becomes usable**. There is still no trustworthy Candidate-0005 kernel stack trace, so a speculative driver/source patch is not justified.

The next non-speculative action is to rerun the ARM64 early-boot binary diagnosis using the exact artifacts that were actually tested:

- exact OS2.0.10 stock baseline artifact: `10754191797`
- Candidate 0005 artifact: `10755230538`

The diagnostic must compare the exact stock and rebuilt Image entry instructions, full ARM64 Image header including declared `image_size`, prefix/first-difference location, appended FDT payloads, and embedded boot-critical config where available. This replaces the stale artifact/baseline references in the previous early-boot workflow.


## Iteration 0008 — 2026-09-24 00:30 +08:00

- Candidate: Candidate 0006 exact OS2.0.10 baseline repack
- Generated by workflow run: `35887467439`
- Artifact ID: `10762987966`
- Boot SHA256: `7deefa462d3ff9eb2b2860561640d84936d24b317dbe15ebf220920b8a9c0d35`
- Boot size: `201326592` bytes
- Kernel Image SHA256: `4aa9995ae5ecbd2e3beb3018cd19a11a80e8970eb96c540874be547d2ecd90c6`
- Target release: `5.4.289-qgki-g4c23b1a30923`
- Device: Xiaomi 11 Lite 5G NE (`lisa`)
- Slot: `_a`
- TWRP: `3.7.1_12-1_Rocky7842`
- Outcome: `black-screen-reboot`
- Note: `閃一屏`
- Collector: `collect_lisa_twrp_logs.ps1 v1.2.0`
- Evidence package SHA256: `6891e09019923087993b68f1ff190bdacbb15beeb7e505cc04f443786c00a296`
- Evidence package bytes: `14084203`

### Persistent evidence

Candidate 0006 still produced no recovery-visible pstore record:

```text
/sys/fs/pstore: empty
/data/vendor/ramoops: absent
```

The current crash-oriented partitions remain byte-for-byte stale relative to Candidate 0005:

```text
oops:
  a78f91d0262e9b37823ee5060fdf5b4a3dd0b34614769149fc428a2a81ac6de2
logdump:
  08cf91fa91ba50db1e55bb54fa1d7efda2cee491c97e2f7fd7f1160d2d825f9a
minidump:
  40bdc781b7e2a2ff8c52e50f9ad713168012b796d60adc8650b32eab2f48ea6d
mdcompress:
  072ce52ce7afcf65859e21f3b11e5df8122690e8ee7863d001aabc99d90a25ea
```

Therefore Candidate 0006 did not commit a new identifiable g4c23 crash record.

### Fresh UEFI/logfs evidence

`logfs` changed to:

```text
sha256=8076f4e77b1f534c93bdd5d0ea5b98b9eb10f3441ee4e30efa9a1afbc7400111
bytes=8388608
```

Mission-mode records again show modified `boot_a` accepted on the unlocked device and kernel handoff reached:

```text
KeyPress:0, BootReason:34
Fastboot=0, Recovery:0
avb_slot_verify: boot_a hash mismatch
VB2: Authenticate complete! boot state is: orange
fatal error is not set
Hyp version: 1
Shutting Down UEFI Boot Services: 4350 ms
Start EBS [4351]
```

Other fresh normal-boot pages likewise reach `Start EBS`. The current failure therefore remains after UEFI ExitBootServices and before a new kernel persistent record becomes available.

### rawdump lineage identification

Iteration 0008 intentionally includes the 200 MiB `rawdump` partition:

```text
rawdump_sha256=605b2027582ca8c4b3c4d1e04d09ecc7b612dc9fe4ca97208c57bc2e3355710c
nonzero_bytes=10954478
```

It is historical, not Candidate 0006. Its Linux banner is:

```text
Linux version 5.4.289-qgki-g5987d69e25da
(builder@pangu-build-component-vendor)
#1 SMP PREEMPT Tue Sep 22 17:43:28 UTC 2026
```

That banner and Image SHA can now be tied exactly to GitHub workflow run `35762412094`:

- workflow: `Probe Lisa stock-only built-in initcall configs`
- reconstruction checkout SHA: `6e568aabc77a06fa787baec1d9e60e4b559874a3`
- artifact ID: `10710943414`
- Image SHA256: `492b0b3910d1425cf434ec946851de73d40003f14adb29e695403bf5b60c2b55`

The rawdump contains that same release/build timestamp and shows it successfully entered Linux, including `Booting Linux`, `setup_arch`, and registration of `ramoops/pstore`. This is positive evidence that the reconstructed lineage can execute well beyond UEFI handoff.

A Git compare between the known-g598 source commit and Candidate-0006 reconstruction source commit `ab491ef6ecd4d35f9edcaa8ad00b568306c6ce64` shows only the later `include/linux/rwsem.h` metadata change at repository level. The much larger behavioral delta is therefore introduced by the later build pipeline (exact OS2.0.10 config, donor overlays, proc ABI adapter, genksyms routing, g4c23 target lineage), not by a wholesale source-tree replacement.

### Decision / controlled A/B

Do not make another speculative driver patch. Build a controlled diagnostic candidate using the exact OS2.0.10 boot baseline but replacing only the kernel with the known-g598 Image `492b0b3910d1425cf434ec946851de73d40003f14adb29e695403bf5b60c2b55`.

This Candidate 0007 is intentionally **not** a final vendor-module-compatible kernel. Its purpose is to isolate whether the exact OS2.0.10 boot baseline itself prevents the known-g598 kernel from entering Linux, or whether the early reset is introduced specifically by the g4c23 composite build path.


## Candidate 0007 — known-g598 exact OS2.0.10 controlled A/B, awaiting device test

- Generated by workflow run: `35890394210`
- Artifact ID: `10763829452`
- Artifact name: `lisa-candidate-0007-known-g598-exact-os2-0-10-ab`
- Boot SHA256: `77690c20d1409f377778d598bb79427b8a195a952ea894549a4b884165a0c43a`
- Boot size: `201326592` bytes
- Kernel Image SHA256: `492b0b3910d1425cf434ec946851de73d40003f14adb29e695403bf5b60c2b55`
- Kernel release: `5.4.289-qgki-g5987d69e25da`
- Kernel source SHA associated with the known-good Image: `6e568aabc77a06fa787baec1d9e60e4b559874a3`
- Exact OS2.0.10 baseline artifact: `10754191797`
- Exact OS2.0.10 stock boot SHA256: `0959eaa1bc914d570792b53207fc9f481b3986c8b9f2a0ec2a76a1fd625a3c1f`

### Purpose

Candidate 0007 is a controlled diagnostic A/B candidate, **not** the final vendor-module-compatible solution.

Its kernel Image is the exact reconstructed g598 Image identified in Iteration 0008 rawdump and GitHub run `35762412094`. That historical device evidence shows this Image entered Linux and registered `ramoops/pstore`.

Candidate 0007 changes only the boot baseline around that known-g598 Image: the kernel is repacked into the exact OS2.0.10 boot v3 baseline while preserving the exact OS2.0.10 ramdisk and all header metadata except kernel size.

### Static validation

```text
KNOWN_G598_IMAGE_GATE=PASS
KNOWN_G598_ARM64_HEADER_GATE=PASS
LISA_CANDIDATE_0007_AB_GATE=PASS

android_magic=PASS
header_v3=PASS
header_metadata_except_kernel_size_preserved=PASS
kernel_hash_exact=PASS
ramdisk_hash_preserved=PASS
partition_size_preserved=PASS
target_release_present=PASS
tail_zeroed=PASS
stale_avb_footer_absent=PASS
```

The Candidate 0007 boot image SHA256 is:

```text
77690c20d1409f377778d598bb79427b8a195a952ea894549a4b884165a0c43a
```

### Interpretation required from the next device test

- If Candidate 0007 again reaches Linux / registers pstore (even if Android later fails because OS2.0.10 vendor modules target g4c23), the EBS-stage regression is isolated to the later g4c23 composite build pipeline rather than the exact OS2.0.10 boot baseline.
- If Candidate 0007 still resets immediately after UEFI `Start EBS` without any new Linux/pstore evidence, the exact OS2.0.10 baseline interaction with the reconstructed Image must be investigated before further g4c23 source changes.

No further speculative kernel mutation is justified until this exact Candidate 0007 is tested on-device.


## Iteration 0009 — 2026-09-24 00:56 +08:00

- Candidate: Candidate 0007 known-g598 exact OS2.0.10 controlled A/B
- Generated by workflow run: `35890394210`
- Artifact ID: `10763829452`
- Boot SHA256: `77690c20d1409f377778d598bb79427b8a195a952ea894549a4b884165a0c43a`
- Boot size: `201326592` bytes
- Kernel Image SHA256: `492b0b3910d1425cf434ec946851de73d40003f14adb29e695403bf5b60c2b55`
- Kernel release: `5.4.289-qgki-g5987d69e25da`
- Device: Xiaomi 11 Lite 5G NE (`lisa`)
- Slot: `_a`
- TWRP: `3.7.1_12-1_Rocky7842`
- Outcome: `black-screen-reboot`
- Note: `閃一屏`
- Collector: `collect_lisa_twrp_logs.ps1 v1.2.0`
- Evidence package SHA256: `58ebd10c6f1a16692164eb27c8843b183a3ef2b6d7df74f62a3e77bbe776927a`
- Evidence package bytes: `14055474`
- Internal package checksum verification: `59/59 PASS`

### Persistent evidence

Candidate 0007 did not create a recovery-visible pstore record:

```text
/sys/fs/pstore: present but empty
pstore_file_count=0
/data/vendor/ramoops: absent
```

The crash-oriented persistent partitions are unchanged from the prior g4c23 tests:

```text
oops:
  a78f91d0262e9b37823ee5060fdf5b4a3dd0b34614769149fc428a2a81ac6de2
logdump:
  08cf91fa91ba50db1e55bb54fa1d7efda2cee491c97e2f7fd7f1160d2d825f9a
minidump:
  40bdc781b7e2a2ff8c52e50f9ad713168012b796d60adc8650b32eab2f48ea6d
mdcompress:
  072ce52ce7afcf65859e21f3b11e5df8122690e8ee7863d001aabc99d90a25ea
rawdump:
  605b2027582ca8c4b3c4d1e04d09ecc7b612dc9fe4ca97208c57bc2e3355710c
```

The rawdump is therefore still the historical g598 payload previously identified in Iteration 0008; Candidate 0007 itself did not overwrite it with a new current boot record.

### Fresh UEFI evidence

The `logfs` partition changed again:

```text
sha256=a90383170301849fb0c8de6889e6930192b41503c6d8be2c92f3b2b70a793604
bytes=8388608
```

Fresh mission-mode pages show the modified `boot_a` accepted by the unlocked bootloader and reaching kernel handoff:

```text
KeyPress:0, BootReason:0
Fastboot=0, Recovery:0
avb_slot_verify: boot_a hash mismatch
VB2: Authenticate complete! boot state is: orange
fatal error is not set
Hyp version: 1
Shutting Down UEFI Boot Services
Start EBS
```

Multiple normal-boot pages reach `Start EBS` before the device returns to recovery/fastboot. Recovery later reports `pureason=0x80011` and `pdreason=0x2`; these remain reboot context only.

### A/B conclusion

Candidate 0007 used the exact same reconstructed g598 Image `492b0b3910d1...` whose historical rawdump proves that it previously entered Linux and registered ramoops/pstore. Repacking that same Image into the exact OS2.0.10 boot baseline still produces the same EBS-stage black-screen reboot with no new kernel record.

Therefore the earlier hypothesis that the g4c23 composite build alone introduced the EBS-stage regression is rejected. The next comparison must focus on the **boot baseline/repack environment** around the known-g598 Image.

The historically used stock-style g598 repack workflow run `35765505149` used:

```text
known_g598_Image_sha256=492b0b3910d1425cf434ec946851de73d40003f14adb29e695403bf5b60c2b55
old_stock_boot_sha256=e6f8c978c2cf0a9473d0ac73cdcf3ffb14747246fdc47f82245c43221eb4cbf1
old_stock_ramdisk_sha256=0dc218f3167e560444634a6a8cf969eb4470bcf452837a3e23bf45ea0a6819ae
old_repacked_boot_sha256=585a69eae9ab0fe1ff028c5e9890c36e4d745778e9d60a9ebdc61649a81c2063
```

Candidate 0007 instead uses the exact OS2.0.10 baseline:

```text
exact_stock_boot_sha256=0959eaa1bc914d570792b53207fc9f481b3986c8b9f2a0ec2a76a1fd625a3c1f
exact_stock_ramdisk_sha256=b85cef81456baa5bdeb6f1ab676cc20682c2ded9e7d49f07f646e10f6c389019
candidate_0007_boot_sha256=77690c20d1409f377778d598bb79427b8a195a952ea894549a4b884165a0c43a
```

### Next action

Do not mutate the kernel source. First compare the old stock baseline `e6f8c978...` against the exact OS2.0.10 baseline `0959eaa1...` byte-for-byte at the Android boot v3 header, cmdline, ramdisk, logical layout, and AVB-tail level. Then re-export/reproduce the historical known-g598 + old-baseline boot as a controlled device-test candidate to confirm whether the baseline difference alone restores Linux entry on the current device state.


## Iteration 0010 — 2026-09-24 01:17 +08:00

- Candidate: Candidate 0008 known-g598 historical OS2.0.16 baseline control
- Generated by workflow run: `35892902113`
- Artifact ID: `10765228960`
- Boot SHA256: `585a69eae9ab0fe1ff028c5e9890c36e4d745778e9d60a9ebdc61649a81c2063`
- Boot size: `201326592` bytes
- Kernel Image SHA256: `492b0b3910d1425cf434ec946851de73d40003f14adb29e695403bf5b60c2b55`
- Kernel release: `5.4.289-qgki-g5987d69e25da`
- Device: Xiaomi 11 Lite 5G NE (`lisa`)
- Slot: `_a`
- TWRP: `3.7.1_12-1_Rocky7842`
- Outcome: `black-screen-reboot`
- Note: `閃一屏`
- Collector: `collect_lisa_twrp_logs.ps1 v1.2.0`
- Evidence package SHA256: `7e1555bbd6e3689ae34b87eaf236379c7a42928ca39827ad2cd24ff3ab7c794f`
- Evidence package logical bytes: `428457149`

### Persistent evidence

Candidate 0008 again did not create a new identifiable Linux crash record. The persistent crash partitions remain byte-for-byte equal to the earlier stale evidence:

```text
oops:
  a78f91d0262e9b37823ee5060fdf5b4a3dd0b34614769149fc428a2a81ac6de2
logdump:
  08cf91fa91ba50db1e55bb54fa1d7efda2cee491c97e2f7fd7f1160d2d825f9a
minidump:
  40bdc781b7e2a2ff8c52e50f9ad713168012b796d60adc8650b32eab2f48ea6d
mdcompress:
  072ce52ce7afcf65859e21f3b11e5df8122690e8ee7863d001aabc99d90a25ea
rawdump:
  605b2027582ca8c4b3c4d1e04d09ecc7b612dc9fe4ca97208c57bc2e3355710c
```

The recovery context reports `pureason=0x80011` and `pdreason=0x2`. These remain reboot-context evidence only.

### Fresh UEFI evidence

The `logfs` partition changed to:

```text
sha256=2cc4fede88849147c8e64cd3d2b29a834aeead27895946aa1671195b1c450236
```

Fresh mission-mode pages again show the unlocked device accepting modified `boot_a` and reaching kernel handoff:

```text
KeyPress:0, BootReason:34
Fastboot=0, Recovery:0
VB2: Authenticate complete! boot state is: orange
fatal error is not set
Hyp version: 1
Shutting Down UEFI Boot Services: 4399 ms
Start EBS [4399]
```

Additional normal-boot pages with `BootReason:0` also reach `Start EBS` before the device returns to recovery/fastboot.

### Candidate 0008 conclusion

Candidate 0008 is a byte-for-byte reproduction of the historical g598 repacked boot that previously existed in the successful g598 lineage, but it does not enter a recoverable Linux logging stage on the device's current firmware state.

The follow-up diagnostic workflow run `35896293207` proved that the historical stock boot baseline is the official `OS2.0.16.0.UKOCNXM` boot:

```text
official_os2_0_16_boot_sha256=e6f8c978c2cf0a9473d0ac73cdcf3ffb14747246fdc47f82245c43221eb4cbf1
official_os2_0_16_ramdisk_sha256=0dc218f3167e560444634a6a8cf969eb4470bcf452837a3e23bf45ea0a6819ae
official_os2_0_16_kernel_release=5.4.289-qgki-g5987d69e25da
OS2_0_16_BOOT_LINEAGE_GATE=PASS
```

That same run found concrete companion-partition drift between historical OS2.0.16 and the current OS2.0.10 device state:

```text
OS2.0.16 vendor_boot=c0a7528e8eacd2a86270ee017dfe90e657f1a0c5c40527869f89e915c2954a5a
OS2.0.10 vendor_boot=6d2c626cc325058ba4c6f16a8f4043978404dfb5ce2f420d770f53d1f5d089f2
vendor_boot_byte_match=0

OS2.0.16 dtbo=db7c50147d8217c41cd86e53dda6e8ce93a5928a8f06ece8da92955a9c0e7ba7
OS2.0.10 dtbo=423828174f86a7aab8823fc1cf5347e9cc97f0f41c246c489bdf5793d79a922e
dtbo_byte_match=0

COMPANION_BOOT_CHAIN_DRIFT=1
```

### Decision

Do not mutate the kernel from Candidate 0008 failure. The first current blocker is the unresolved **OS2.0.16 versus OS2.0.10 companion boot-chain state** around the same known-g598 kernel Image. The next safe diagnostic is to compare the two versions' `vendor_boot` ramdisks/modules, embedded DTB, and `dtbo` entries before requesting another device flash.
