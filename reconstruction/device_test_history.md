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
