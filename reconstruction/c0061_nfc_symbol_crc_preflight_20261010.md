# Candidate0061 NFC module CRC preflight and device ABI boundary — 2026-10-10

## Context and verified technical correction

The user tested kernel 5.4.302 Candidate0061 with stock vendor_a EROFS containing two NFC modules with **5.4.289** vermagic. A release-label mismatch **alone is insufficient proof of a module load failure**, especially with `CONFIG_MODVERSIONS=y`. Linux may ignore the release-token portion of vermagic when CRC versioning is available and require the remaining flags / required exported symbol CRCs to match. OEM kernels can differ; no force-loading, vermagic patching, AVB bypass or SELinux weakening is justified.

Authoritative background:
- https://source.android.com/docs/core/architecture/kernel/loadable-kernel-modules — module CRC checks for target kernel and official rationale for small LTS uplifts.
- https://source.android.com/docs/core/architecture/kernel/abi-monitor — exported symbols' CRCs can be checked using `Module.symvers`.
- https://android.googlesource.com/kernel/common/+/08d19f51f05a68ce89a289320ce4ed96e757df72/kernel/module.c — module-version/CRC checks; kernel provenance and configuration matter.
- https://android.googlesource.com/platform/system/core/+/android16-qpr2-release/libmodprobe/libmodprobe.cpp — `ListModules` iterates dependency collection, distinct from explicit `modules.load` ordering. Not proof of the exact Xiaomi modprobe binary's output.

## New actual CI verification

Source: complete existing integrated C0061 build Action `37655937871`, compiled artifact `lisa-c0061-integrated-302-evidence-a1`, `nfc_i2c.ko` SHA256 `aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b`, kernelrelease `5.4.302-qgki-lisa-c0061-rfb3b3c2-by-Tim0320`.

New runnable Python CRC gate `reconstruction/scripts/candidate_0061_module_crc_preflight.py` (commit `a1169ef`) parses **actual** ARM64 ELF `__versions`, decodes 8-byte CRC + 56-byte symbol records, and compares every imported symbol to the actual integrated build `kernel/out/Module.symvers`. It refuses missing symbols, CRC differences, duplicate/conflicting exports, missing modversion section, ELF and SHA mismatch, or wrong module release. Runs `llvm-objcopy` only on a disposable module copy; the original stays byte-exact. It explicitly reports `device_5_4_289_modules_analyzed=false`.

New GitHub workflow `.github/workflows/verify-lisa-candidate-0061-nfc-crc.yml` (commit `f4d3d0f`), first Action `38056503148` **SUCCESS**: actual compiled module checks and deliberate corruption of `module_layout` CRC to verify the negative control fails. On the uploaded module used in the local checker test, `__versions` exposes **71** imported CRC entries; final pass values are to be read from the Action artifact, not inferred from a synthetic fixture. A follow-up update `6c8199a` arranges for the **actual integrated `Module.symvers`** to be included in the CI evidence artifact, so the next check can compare recovered 5.4.289 *device binaries* to the exact built 5.4.302 CRCs without needing a new kernel compilation.

**Strong boundary:** a PASS checks the guarded CI NFC module against the **same build's** exported symbols. This is a targeted build consistency check and does **not** prove the two stock vendor NFC modules are ABI-compatible, or prove either loaded on the phone, or solve the reboot.

## Decisive missing input

The previous TWRP v1.4.0 ZIP recorded `sha256sum` and vermagic for vendor NFC files but did **not** copy the `.ko` binaries, so their imported `__versions` CRCs cannot be compared yet. Read-only copy both exact files from actual `vendor_a` only:
- `/vendor/lib/modules/nfc_i2c.ko` (QGKI, expected SHA256 `b37dae41aad83b6adaa1f2a16253d2a8ca931b83a534fd5fb57ceaea2424bc68`)
- `/vendor/lib/modules/5.4-gki/nfc_i2c.ko` (GKI, expected SHA256 `bb1e8994d0ddf0b15bd038457a850b2a8b5c7b74e1816b97dea5623c2ea5c80b`)

Collect from **TWRP ADB=recovery**, vendor_a EROFS `ro` mounted to RAM-backed `/tmp`; PowerShell fixed first command `Set-Location "D:\1.ROM_Prot\lisa\pull_log"`, output ZIP under same folder. Do not attempt Android ADB if inaccessible. Upload privately to conversation, not a public GitHub commit or Actions artifact (OEM module binaries may be proprietary). Validate hashes before comparison.

After this input, compare actual vendor modules' `__versions` CRCs to new C0061 build's exported `Module.symvers` for each imported symbol, distinguish missing vs changed vs matching CRC and other vermagic flags, prioritize actual loader branch and first-fault if still needed, and choose an AVB/EROFS-safe rollback plan. No same-boot reflash or rebuild until a justified source/module deployment change is ready.

Status classification: `CI_NFC_COMPAT_WITH_SAME_BUILD_EVALUATED`; `STOCK_VENDOR_NFC_COMPATIBILITY_PENDING_DEVICE_BINARY`; `CURRENT_BOOT_CAUSE_UNVERIFIED`. No new boot.img packaged.
