# Candidate0061 NFC imported-symbol export-provider verification — 2026-10-10

**Classification:** `STATIC_NFC_IMPORT_PROVIDERS_KNOWN`; **not** `DEVICE_NFC_LOAD_PASS`, **not** `BOOT_PASS`.

## Source and integrity

- **Physical-device, private:** previously user-supplied `lisa_nfc_crc_20261010-215518.zip`; two authentic stock vendor_a NFC ELF64 AArch64 modules. SHA256 of `/vendor/lib/modules/nfc_i2c.ko` (QGKI) `b37dae41aad83b6adaa1f2a16253d2a8ca931b83a534fd5fb57ceaea2424bc68`; SHA256 of `/vendor/lib/modules/5.4-gki/nfc_i2c.ko` (GKI) `bb1e8994d0ddf0b15bd038457a850b2a8b5c7b74e1816b97dea5623c2ea5c80b`.
- **Actual paired C0061 5.4.302 kernel export table:** `kernel/out/Module.symvers` from Direct-302 successful build run [37655937871](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/37655937871), independently preserved by CRC preflight run [38056564905](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38056564905) artifact `11672061727`. Source file 830233 bytes, 14434 unique symbol names including 14059 exports from `vmlinux`.
- Method: verified both `.ko` SHA256, extracted their *actual* ELF `__versions` (64-byte entries) into RAM/tmp using `llvm-objcopy`, and joined **each imported symbol name** against the same-build `Module.symvers` export owner/module and 32-bit CRC. Computation was offline; **no proprietary OEM binary has been committed to public GitHub, sent to Actions, loaded on phone, or changed on vendor partition**.

## New decisive counts

| Original stock `nfc_i2c.ko` | Imported CRC records | Symbols exported by `vmlinux` | Symbols supplied by other `.ko` | Missing exports | Identical CRC | CRC mismatch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| QGKI `/vendor/lib/modules/` | **71** | **71** | **0** | **0** | **71** | **0** |
| GKI `/vendor/lib/modules/5.4-gki/` | **68** | **68** | **0** | **0** | **36** | **32** |

Thus **the NFC imports themselves have no declared dependency on any other compiled `.ko` export in C0061**: all names resolve to built-in `vmlinux` exports. For this specific NFC module, a supposed missing intermediate `.ko` provider cannot explain a direct import resolution failure. This does **not** prove the *entire Android module set* has no inter-module dependencies (manifest graph already documents 211 QGKI edges, 741 GKI edges).

- QGKI's all-71 CRC agreement with `vmlinux`, including `module_layout=0xba39cbb8`, further reduces the likelihood of a **static version/CRC rejection** of *stock QGKI NFC* by the Candidate0061 Kernel. Module signature, namespace, loader flags, Android runtime state, init/SELinux decisions, and actual NFC functionality are still untested.
- GKI's 32 different 32-bit CRCs (including `module_layout`) constitute an **actual symbol-version mismatch** against that same `vmlinux`; normal modversions checking can reject that alternative module. Neither rejection nor use of the GKI branch was observed on device; a rejection by itself does not prove a full-system reboot cause.
- The separate guarded 5.4.302 CI-built NFC module has 71/71 self-build import CRC match; that module is still **not present in either observed EROFS vendor file** and is **not implicitly installed by the fixed-region `boot.img`**.

## CI implementation/recovery

- Export-provider checker `reconstruction/scripts/candidate_0061_module_provider_gate.py` (commit `ea04448`) categorizes imported symbol owners as `vmlinux` or modules; designed to report source-side exports separately from Android load.
- Initial provider-workflow integration at `c9f6871` corrupted YAML text and yielded no jobs in GitHub run `38058881768` (invalid workflow configuration). **Not a kernel or ABI failure.**
- CI fixed by restoring the last known successful workflow and adding a bounded independent provider step at `fd04d8e`; subsequent run [38058926584](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38058926584) **SUCCESS**, including existing 71/71 guarded NFC CRC gate, provider inspection and deliberate CRC-tampering negative control. This run is inspection/static only; no new kernel/boot.img was built.
- Detailed raw OEM modules are deliberately not stored in GitHub. Counts above were independently derived offline using user supplied private modules.

## Revised next-action logic

1. Continue checking actual first candidate returned by Xiaomi `/vendor/bin/modprobe -l` and the single first-probe failure condition in `vendor_modprobe.sh`, not the first `modules.load` line. Original QGKI `nfc_i2c.ko` itself is not a convincing *CRC* boot blocker. The GKI path remains a conditional broad-module mismatch risk.
2. Evaluate other high-dependency modules and the Android runtime first-fault only when evidence is available; avoid falsely extrapolating NFC provider results to 107 or 227 OEM binaries.
3. In the stock Direct-302 build `.github/workflows/build-lisa-candidate-0061-integrated-302.yml`, `boot.img` packages only the new kernel Image into a stock fixed region while preserving stock ramdisk/AVB fields. Its separately compiled guarded `.ko` is staged as an artifact, **not installed into EROFS vendor**. Any actual deployment needs verified partition/kernel identity, safe rollback/AVB plan and confirmation of module load path; no blind vendor rewrite, SELinux/thermal weakening, or repeated unchanged-boot flash.
4. No user log re-collection is warranted for the exact NFC CRC/provenance already closed. If later device evidence is necessary, begin commands with `Set-Location "D:\1.ROM_Prot\lisa\pull_log"`; direct Android ADB=device logs should only be requested if technically available.

**No new boot.img**, **not `boot打包可準備測試`**.
