# Lisa Candidate 0008 — known-g598 old-baseline control

Status: **static validation complete; real-device test required**.

Candidate 0008 is a controlled baseline experiment. It does not change kernel source. It combines the exact known-g598 reconstructed Image with the historical stock boot baseline that was used by the older g598 repack workflow.

## Provenance

- Workflow run: `35892902113`
- Workflow job: `107289510550`
- Artifact ID: `10765228960`
- Artifact name: `lisa-candidate-0008-known-g598-old-baseline-control`
- Artifact ZIP digest: `sha256:b248c0fc9edd03d26e3527973cd2aae1b25e6517aa6be167f9704c26d1116a0b`
- Artifact size: `42085124` bytes
- Candidate `boot.img` SHA256: `585a69eae9ab0fe1ff028c5e9890c36e4d745778e9d60a9ebdc61649a81c2063`
- Boot partition size: `201326592` bytes
- Known-g598 Image SHA256: `492b0b3910d1425cf434ec946851de73d40003f14adb29e695403bf5b60c2b55`
- Kernel release: `5.4.289-qgki-g5987d69e25da`

## Baseline comparison

Historical old baseline:

```text
boot_sha256=e6f8c978c2cf0a9473d0ac73cdcf3ffb14747246fdc47f82245c43221eb4cbf1
kernel_size=51436032
ramdisk_size=19883180
ramdisk_sha256=0dc218f3167e560444634a6a8cf969eb4470bcf452837a3e23bf45ea0a6819ae
os_version_raw=436208027
header_size=1580
header_version=3
reserved=(0,0,0,0)
cmdline=<empty>
logical_end=71327744
tail_nonzero=367
avb_footer=1
header_page_sha256=2fb1bb38523f4e50c3f3996bc8d3710e95e8e14b1ad8c4a74ea7b62dcee5317a
```

Exact OS2.0.10 baseline used by Candidate 0007:

```text
boot_sha256=0959eaa1bc914d570792b53207fc9f481b3986c8b9f2a0ec2a76a1fd625a3c1f
kernel_size=51436032
ramdisk_size=19883182
ramdisk_sha256=b85cef81456baa5bdeb6f1ab676cc20682c2ded9e7d49f07f646e10f6c389019
os_version_raw=436208022
header_size=1580
header_version=3
reserved=(0,0,0,0)
cmdline=<empty>
logical_end=71327744
tail_nonzero=368
avb_footer=1
header_page_sha256=e65cea90dc9c76c5832e99d1dceb695ffb4234bd48a5e1ad3820cefc1e252ca4
```

The Android boot v3 header page differs in only two byte positions before payload differences are considered:

```text
header_page_diff_bytes=2
header_page_first_diff_offsets=0x0c,0x10
```

These offsets correspond to the ramdisk-size field and OS-version field. The cmdline, boot header version, header size, reserved words, kernel size, logical end, and AVB-footer presence are equal. The ramdisk payload itself is different and is the largest meaningful baseline change for the controlled device test.

## Exact reproduction gate

The workflow reproduced the historical g598 + old-baseline boot byte-for-byte:

```text
boot_img_sha256=585a69eae9ab0fe1ff028c5e9890c36e4d745778e9d60a9ebdc61649a81c2063
check_old_stock_boot_exact=1
check_known_g598_image_exact=1
check_old_ramdisk_exact=1
check_historical_boot_sha_exact=1
check_partition_size_preserved=1
check_header_metadata_except_kernel_size_preserved=1
check_target_release_present=1
check_tail_zeroed=1
check_stale_avb_footer_absent=1
LISA_CANDIDATE_0008_REPRODUCTION_GATE=PASS
LISA_CANDIDATE_0008_CONTROL_GATE=PASS
```

## Interpretation

Candidate 0007 showed that the known-g598 Image still resets immediately after UEFI `Start EBS` when wrapped in the exact OS2.0.10 boot baseline. Candidate 0008 changes only that baseline back to the historical old baseline while keeping the exact same known-g598 Image.

The next safe step is therefore a real-device test of Candidate 0008. No further kernel-source or build-pipeline mutation is justified before that result.

- If Candidate 0008 reaches Linux or creates a new current g598 pstore/ramoops record, the early reset is strongly tied to the boot-baseline/ramdisk environment rather than the g598 kernel Image itself.
- If Candidate 0008 still resets after `Start EBS` with no new Linux record, the old-vs-exact baseline difference is not sufficient, and the investigation should move to device state / handoff conditions that are outside the kernel-source comparison.

Use the artifact `10765228960` and verify the flashed `boot.img` SHA256 is exactly `585a69eae9ab0fe1ff028c5e9890c36e4d745778e9d60a9ebdc61649a81c2063` before testing.