# Candidate0061 - authenticated OEM Oops module-route correlation

**Date:** 2026-10-12 (Asia/Taipei)  
**Result:** `STRONG_QGKI_LOADED_SET_CORRELATION_NOT_LOADER_ATTESTATION`  
**Release gate:** `NOT_FLASHABLE`; device runtime outcome of **new** diagnostic Boot remains `UNKNOWN`.

## Source and integrity

This is newly rederived from the user's **original private Library archives**, not a copied claim from earlier notes. All ZIP CRCs and SHA-256 source identities were checked. No files were pushed to the handset, and no private OEM dump is published.

- Original TWRP ZIP: `lisa-twrp-iter-0001_20261010-224509_boot_038e35371c97.zip`; SHA256 `1c27309687fe176744f98353fc77900837c7d95590c8b3e96f5db0483e898e43`.
- OEM 16 MiB raw `lisa_oops_iter0001.bin`: SHA256 `0e034b59946d562344dfb0295ce3cd0e6141f31bf4b685829ff2224f5b277e47`.
- Vendor module manifest ZIP: `lisa_nfc_module_configs_20261010-212249.zip`; SHA256 `3a8717640a28b8facbd46e59bf796a577b462bbce1cc7d521d768e7218b6ac0b`.
- Independently validated MTD Oops memory layout: **8 records, exactly 2 MiB each**, with the expected header magic at offset +4 in each record. Panic is in **record index 1**, not merely found by scanning unbounded raw bytes.
- This record itself has **2 kernel-clock segments** (an older tail followed by timestamps restarting at zero). The following facts all derive from the **second, same-clock segment**. Different historical segments were not merged into one presumed boot.

## Directly recovered runtime facts (the original failed C0061 Boot)

| Observation | Actual value |
| --- | --- |
| Running Kernel | `5.4.302-qgki-lisa-c0061-rfb3b3c2-by-Tim0320` |
| Loaded modules named in panic (`Modules linked in`) | 59 |
| Modules in that line present **only** in QGKI manifest | **41** |
| Modules in that line present **only** in GKI manifest | **0** |
| Separate `LISA0054_MODULE` load markers | 62 unique names |
| Load markers present **only** in QGKI manifest | **42** |
| Load markers present **only** in GKI manifest | **0** |
| Earliest observed QGKI-only load marker | `fc0013` at boot +14.738538 s |
| NFC module load marker | `nfc_i2c` at +15.372057 s |
| NFC I2C probe successfully completed | +15.570856 s |
| `nqnfcinfo` -> `nfc_dev_open` -> `mutex_lock` Panic | +41.797828 s |

Examples of loaded QGKI-only modules: `xc4000`, `xc5000`, `llcc_perfmon`, `fc0013`, `mt2063`. The list of 41 QGKI-only modules at the fatal panic and zero GKI-only modules gives **strong positive evidence of an active QGKI module set on this original boot**, unlike earlier static-only investigations. It does **not** independently prove the proprietary vendor script's exact exit status or the filesystem path/bytes for the loaded `nfc_i2c.ko`.

The loader's very first `modprobe -l` candidate **remains UNKNOWN**; a QGKI-only module appearing earlier than NFC does not absolutely prove which process initiated it, although NFC-first is less consistent with this observed timeline.

## Separate failures correctly distinguished

1. Boot +10.577 s: Android init attempted `/lib/modules/5.4-gki/hwkm.ko`, followed by a `module_layout` CRC/version disagreement. This is an **independent first-stage GKI ramdisk load**, not proof that the later OEM vendor loader selected whole-directory GKI fallback.
2. Boot +17.041 s: Android `init` recorded **Exit 1** for an explicit `/vendor/bin/modprobe -a -d /vendor/lib/modules` **audio/DSP** module list. It is a **separate init exec**, not a recorded failed initial probe within `vendor_modprobe.sh`.
3. The original fatal reboot is directly explained by the saved NFC char-device invalid-pointer Oops at +41 s. The already-built guarded NFC source mitigates this pointer shape, but success on device has not been demonstrated.

## How this changes the NFC built-in blacklist decision

The proposed offline Boot from existing Action 38062935154 (SHA256 `a4918b11c1f7ad2ae8df7444c587a3613afade2c91d800e494f06b331cb989c8`) has `CONFIG_NFC_QTI_I2C=y` and a Boot v3 `module_blacklist=nfc_i2c` cmdline. Its tested content is **not** the same as the old recorded failing Boot.

- The actual frozen kernel code `kernel/module.c` has `core_param(module_blacklist, ...)` and returns `-EPERM` before completing `load_module` for a blacklisted name. A built-in NFC initcall is not a loadable module.
- Existing built-in config has `CONFIG_CMDLINE_EXTEND=y`, `# CONFIG_CMDLINE_FORCE is not set`, `CONFIG_CMDLINE="ramoops_memreserve=4M"`; `drivers/of/fdt.c` appends DT `/chosen/bootargs` in that configuration. Whether this handset's bootloader forwards the modified Boot v3 parameter remains unverified.
- Because the old failed boot strongly used a QGKI module set, the hypothesis of universal forced GKI fallback on every normal boot is **less supported than before**, but **the new blacklist could still change initial-probe return codes**. Exact OEM `modprobe -l` ordering and the new Boot runtime must not be fabricated.
- OEM AVB chain/rollback/A-B recovery validation remains missing. Neither an already unlocked bootloader nor static Boot integrity guarantees a reversible real-device test.

## Next practical engineering gates

1. Use the **existing 16 MiB OEM Oops backend** for any future test; do not require pstore or a functioning Android ADB. Always split MTD records and clock resets before attributing logs to the current Boot.
2. If available without touching partitions, retrieve genuine OEM modprobe binary/listing and `modules.blocklist`/`modules.alias` to identify the first synchronous probe. Until then, mark `FIRST_PROBE=UNKNOWN`, not a hypothetical NFC-first PASS/FAIL.
3. Keep diagnostic Boot **NOT FLASHABLE** pending independently verified effective cmdline, AVB/rollback, real dual-slot backup/restore, and controlled test authorization. Do not alter vendor EROFS, vbmeta, SELinux, thermal, or frozen C0059.
4. Prioritize the **NFC char-device crash fix** on the known QGKI route; treat the separate first-stage GKI `hwkm` ABI error and audio batch failures as independent secondary investigations.

## Reproducibility

Run the accompanying standard-library-only verifier against copies of the two original source ZIPs:

```sh
python3 c0061_oem_oops_module_route_gate.py --self-test
python3 c0061_oem_oops_module_route_gate.py \
  --oops-zip lisa-twrp-iter-0001_20261010-224509_boot_038e35371c97.zip \
  --module-zip lisa_nfc_module_configs_20261010-212249.zip \
  --json c0061_oem_oops_module_route_20261012.json
```

The verifier does not read any Android device, execute the proprietary loader or ship any private raw logs. It returns `flash_authorized=false` unconditionally.