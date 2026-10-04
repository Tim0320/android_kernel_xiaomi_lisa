# Candidate0057: repair the stock-versus-donor flash contract check

## Observed failure, not an inferred compiler error

Build package fdf1a54e3e254ce32a3078cfd57b4ee1726f9adf,
Run37177089277, build111361868869 completed Build and package successfully.
Verify failed at 2026-10-04T04:54:57Z with:

```
RuntimeError: Candidate0057 QTI flash -> battery module import not proven
```

The first traceback is in candidate_0057_ownership_patch.py:216. The raw-latch,
UFS 7/7 plus compiled LUN0 call, power providers, and prior shell gates passed.
The verified boot upload was skipped. The boot checksum in the failure
manifest is not permission to release the unverified artifact.

The existing large job log was exported through a read-only diagnostic Action:
Run37180938581, artifact11295074857, ZIP SHA256
`dc948c3c5d2fdf237a6f02efe3c0f634cef968f79d2816b1b226241b3fd37355`.
Its job.log lines6850-6867 show the exact failure. This diagnostic Action is not
a new boot build, and its success does not repair the kernel.

## Incorrect assumption in the verifier

The rebuilt donor flash and stock runtime flash are different implementations.
Pinned donor include/linux/soc/qcom/battery_charger.h blob
67660c72acec853ba6f616a49469c17fc1a5596d declares an external
qti_battery_charger_get_prop only with CONFIG_QTI_BATTERY_CHARGER enabled.
Otherwise it provides a static-inline -EINVAL fallback. The preserved generic
charger setting is disabled; it must not be enabled just to satisfy this gate
and accidentally introduce a competing generic charger driver.

The original runtime vendor flash is not replaced by these donor probe modules.
Pinned normal-QGKI stock flash actually imports the function and depends on
qti_battery_charger_main_k8. Its import CRC and the battery export CRC are both
0x47653d56, with an actual text function and __ksymtab export in the battery
module. Forcing the generic donor to show this same dependency was wrong.

## Replacement verification, not a skipped check

Keep all 84 camera/HWID/flash ownership checks, the donor camera imports,
flash-selector checks, CFI, module-loader policy, UFS and power gates unchanged.
Replace only the misdirected flash-import assertion with:

- Exact SHA256/ELF/architecture pins for stock flash and battery reference files.
- Stock flash dependency metadata plus undefined-function presence.
- Matching consumer and provider CRC, exported-code presence, and no competing
  vmlinux provider for the property getter.
- Every other stock flash import and every battery import checked against the
  new build's Module.symvers, including module_layout and typed power providers.
- Confirm the donor header is still pinned and the generic charger remains off.
- Record separately that the donor uses its disabled generic-driver fallback.

References are Jiovanni-dump/xiaomi_lisa_dump at
2dbe7b5569ed49cc2c6649a7b313d4a092755034, normal vendor/lib/modules (not 5.4-gki):

| File | SHA256 |
|---|---|
| leds-qti-flash.ko | e935c3627c6e57515af45ed4e0582a07cd06f71f1d3c82e013c107343a0b89bc |
| qti_battery_charger_main_k8.ko | 9f2f5f40484a765b5c81c63a83324ea8740eca1fc4c5ca9db321d1573a4609df |

This public OS2.0.3 reference is not a byte-exact readback of the user's OS2.0.8
phone. No phone modules or protected partitions are installed/modified by the
verification helper. Runtime Wi-Fi/camera/flash validation remains pending.

## Tests and rebuilding

Local tests: eleven positive/negative gate tests passed. Wrong CRC, missing
imports/dependencies/exports, non-code provider, duplicate core provider,
missing core provider and corrupt reference bytes are rejected.

With the actual pinned reference binaries and independently checksum-verified
Candidate0056 artifact11283188386, all45 other flash imports and78 battery
imports matched, plus the explicitly paired0x47653d56 property edge. This is a
baseline ABI test, not proof that the new0057 build or hardware test passed.
Full inherited Python/source-transform preflight and505 power host inputs
passed. Five invalid commit IDs were rejected by the identity generator.

The user's previously pending -by-Tim0320 suffix is now applied to the recipe
for this necessary rebuild; no binary string patch or fake Linux version is
used. The release is5.4.289-qgki-lisa-c0057-r<actual package SHA7>-by-Tim0320.
The earlier failedfdf1a54 run never contained this terminal suffix.

Both build and verify now preserve tee logs with pipefail; failure artifacts
retain config, symbol maps and donor flash bytes so a future failure does not
require another full-console export. Only the success path uploads boot.img.

Re-read current main/Actions for the new package SHA and Run; document commits
and the failure-log diagnostic run are not boot releases. Continue the same
hourly Lisa task and per-build2/2/5-minute observer. No5.4.302 upgrade, graphics
parameter change or unrelated runtime driver change is introduced here.
