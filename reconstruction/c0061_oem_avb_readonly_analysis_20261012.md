# Candidate0061 OEM AVB read-only capture — 2026-10-12

Source: user-supplied `lisa-oem-avb-readonly-20261011T171650Z.zip` (no serial; original raw partition images remain outside the public GitHub repository).
ZIP SHA256: `b891928e752053bc530ea5f85cf03192f72c911a043af17e64e36eb98a47618d`.
Four 131072-byte images, manifest SHA256 and ZIP CRC independently verified.

| Partition | SHA256 | Flags | Self-contained SHA256 / RSA signature | Header rollback index |
| --- | --- | ---: | --- | ---: |
| vbmeta_a | f2a3f3372017148eb86c1acde73b6d3bb6524bdca57b5d6317f8150ac9da48b5 | 3 | FAIL / FAIL | 0 |
| vbmeta_b | f2a3f3372017148eb86c1acde73b6d3bb6524bdca57b5d6317f8150ac9da48b5 | 3 | FAIL / FAIL | 0 |
| vbmeta_system_a | 115990a9b5def935f8c458207678cd03b7086eb23539dca1659d45c292e5dfd1 | 0 | PASS / PASS | 1756684800 |
| vbmeta_system_b | 115990a9b5def935f8c458207678cd03b7086eb23539dca1659d45c292e5dfd1 | 0 | PASS / PASS | 1756684800 |

Observed slot `_a`, reported boot state `orange`; device unlock property was absent.
Top-level flags=3 means HASHTREE_DISABLED (bit0) and VERIFICATION_DISABLED (bit1) in the captured image. In memory-only hypothetical verification, toggling only the flags field from 3 to 0 restores SHA256 authentication-block hash match and RSA-2048 PKCS#1 v1.5 SHA256 verification against the embedded public key; no partition or source image was written.
Chained descriptor: `vbmeta_system` uses rollback index location 2; top-level image rollback index=0 and system image rollback index=1756684800. Same embedded public key blob SHA256 in all images: `c5d3c71bc70d58e3e0409ca9d9b34c0dbac1d2f09a5de948a4b8f090f1926965`.

**Scope limitation:** Self-contained signature validation does not prove OEM root-of-trust acceptance, actual hardware rollback counters, or current bootloader locking status. AVB flag alteration is an observed device state, not an authorized modification or a packaging remedy. No OEM private signing key is available. Original Candidate0061 packaged boot has embedded AVB digest mismatch and cannot be marked flashable. The guarded NFC module is CRC 71/71 same-build in CI but NOT deployed; runtime QGKI/GKI loader branch remains unknown. Do not disable AVB, rewrite EROFS vendor, flash a boot image, or claim device PASS from these observations.

Next gates: trusted OEM vbmeta/key provenance; read-only bootloader lock/rollback state where supported; verified matching boot/vendor_boot/dtbo/vbmeta chain and backed-up A/B rollback; runtime NFC loader identity and reversible deployment procedure.
