# Lisa Candidate 0011 device-test gate

Candidate 0011 is the minimum early-config control after the healthy stock-vs-Candidate 0008 A/B isolation.

## CI provenance

- Workflow run: `35960541308`
- Workflow head: `9de365314b114365fe4f15a3c4a4db65c96177bf`
- Artifact ID: `10793021515`
- Artifact name: `lisa-candidate-0011-stock-early-config-v2`
- Artifact digest: `sha256:f1a158d71e14da1b2b62f192da2831eb8c1b26c07aa19c168f1a7673601cea50`
- Source commit: `6e568aabc77a06fa787baec1d9e60e4b559874a3`
- Candidate Image SHA256: `1b587d60fbe5530102c1aa6430fea3232796c8c9265e002f63dd202697c6f09e`
- Candidate boot.img SHA256: `6a5eb2b97bffa0377e1f41ac66f4aa1800e88a6e6ab6f4f959701992f8c0868b`
- boot.img size: `201326592` bytes

## Static validation

The workflow completed successfully and all Candidate 0011 build/repack/static gates passed.

```text
CONFIG_ARM64_LSE_ATOMICS=y
CONFIG_ARM64_USE_LSE_ATOMICS=y
CONFIG_QCOM_WATCHDOG_BARK_TIME=20000
CONFIG_QCOM_WATCHDOG_PET_TIME=15000
LSE_ASSEMBLER_PROBE=PASS
HAVE_QCOM_MINIDUMP_ENCRYPT=0
CANDIDATE_0011_REPACK_GATE=PASS
LISA_CANDIDATE_0011_STATIC_GATE=PASS
```

The donor Kconfig cannot represent `CONFIG_QCOM_MINIDUMP_ENCRYPT`; Candidate 0011 therefore does not fabricate that hidden/unavailable symbol. It aligns only early-config differences that are actually representable in the exact donor source.

The repack checks prove:

```text
check_partition_size_preserved=1
check_ramdisk_exact=1
check_header_except_kernel_size_exact=1
check_kernel_payload_exact=1
check_tail_zeroed=1
```

Therefore the controlled variable remains the kernel Image.

## Required real-device state

Keep unchanged:

- `reconstruction/stock/stock-Image-3.09/` firmware state
- `stock-Image-3.09` vendor_boot
- `stock-Image-3.09` dtbo
- current vbmeta/device state used by the successful stock control
- user's actual TW/global OS2.0.8.0 ported `super`
- active slot A

Change only `boot_a` to Candidate 0011 `boot.img`.

```text
fastboot set_active a
fastboot flash boot_a boot.img
fastboot reboot
```

Do not change vendor_boot, dtbo, vbmeta, super, or firmware for this control.

## Device-test decision

If Candidate 0011 boots Android, record `adb shell uname -a` and `adb shell getprop sys.boot_completed` before changing any partition.

If Candidate 0011 still black-screen-reboots, collect the same TWRP evidence bundle immediately before changing any other partition. The next source mutation must be driven by that fresh device evidence; no further speculative kernel change is justified before the device result.
