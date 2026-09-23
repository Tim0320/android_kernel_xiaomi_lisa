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
