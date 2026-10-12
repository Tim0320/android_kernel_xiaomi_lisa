# Lisa Candidate0061: original Android kernel cmdline provenance and safer next-build draft

Date: 2026-10-12 (Asia/Taipei). Policy: **LOCAL_BUILD_PRIMARY + CI_AUDIT_ONLY**. Release gate: **BLOCKED_NOT_FLASHABLE**.

## New direct evidence

Reprocessed three actual immutable archives, not just old reports, with the reproducible local `c0061_cmdline_provenance_gate.py`:

| Input | Identity | Finding |
| --- | --- | --- |
| Original full C0061 build | Action 37655937871, artifact 11500359180; ZIP SHA256 `74601294086e554adf5a1869eff2e08fd9c53133c1db76f85031483d09237a4c` | The genuine **crashed** C0061 `rfb3b3c2` target config has `CONFIG_CMDLINE="ramoops_memreserve=4M"`, `CONFIG_CMDLINE_EXTEND=y`, not FORCE, NFC=m; Boot v3 header cmdline is **empty**. Boot SHA256 `038e35371c9705fd44908157ce456576100dfcb07f14ef60aa31e3b669c2eed6`. |
| Original handset OEM Oops | 2026-10-10 22:45 user TWRP ZIP SHA256 `1c27309687fe176744f98353fc77900837c7d95590c8b3e96f5db0483e898e43`, OEM Oops SHA256 `0e034b59946d562344dfb0295ce3cd0e6141f31bf4b685829ff2224f5b277e47` | **Same MTD record** containing the 41.8s `nqnfcinfo` NFC Kernel Panic has a real Android **Kernel command line** beginning `ramoops_memreserve=4M`. The actual command line also includes `block2mtd`, `mtdoops.mtddev=0`, `mtdoops.record_size=2097152`, `mtdoops.dump_oops=0`, and `printk.always_kmsg_dump=1`. The full line, including device-specific identifiers, was deliberately **not exported**. |
| NFC guarded built-in diagnosis | Full build Action 38062935154, local repack ZIP SHA256 `c4181a81973f98c499482525fa08172ab896bd42f1b986db1a973ebee085f6c5` | Source config has the same built-in ramoops prefix, `CONFIG_CMDLINE_EXTEND=y`, `CONFIG_NFC_QTI_I2C=y`; new **header-only** diagnostic Boot SHA256 `a4918b11c1f7ad2ae8df7444c587a3613afade2c91d800e494f06b331cb989c8` has v3 header cmdline `module_blacklist=nfc_i2c`, but there is **no device runtime confirmation** that this header change reached the effective kernel command line. |

All archive SHA256, ZIP CRC, embedded Boot SHA, Boot-v3 header fields, matching source configs, and the original per-record NFC Panic provenance passed. Standard-library-only synthetic tests covered positive and negative headers/configs.

**New conclusion:** The **original failed C0061** Kernel had a working built-in `CONFIG_CMDLINE` prefix; the blank original Boot-v3 cmdline was not required for that prefix. Exact device behavior of the **new modified header** remains UNKNOWN. The frozen `drivers/of/fdt.c` with `CONFIG_CMDLINE_EXTEND` concatenates the configured cmdline and DT `/chosen/bootargs`, but another build must independently verify its effective runtime line. This is stronger source+device evidence than a header-only static inspection.

## Next local-build path (prepared, NOT performed)

A separate, output-only `c0061_embedded_cmdline_config_prepare.py` was executed against the **exact** source `.config` of successful NFC=y Action 38062935154 (SHA256 `80b3d3f814a2d6d8e44ff8b9e1f8eec25723d8c92c2a7726f8df81596f6e1795`). It produces `C0061_NFC_BUILTIN_EMBEDDED_BLACKLIST_UNBUILT.config`, a diff, and JSON manifest. **Exactly one Kconfig line changes:**

```diff
-CONFIG_CMDLINE="ramoops_memreserve=4M"
+CONFIG_CMDLINE="ramoops_memreserve=4M module_blacklist=nfc_i2c"
```

This config is a **DRAFT** only: not an Image, not a Kernel build, not a Boot, and not flashable. The draft can remove dependency on Boot-v3 header forwarding **if and only if a new full Kernel is built and its effective runtime command line is subsequently observed**. The existing source configuration, OEM Oops logging, NFC=y and security settings are otherwise retained in this single-line static draft. Actual build recipe must assign unique Kernel identity, run full frozen C0059 control / Direct-302 uplift, KMI/ABI/modpost and packaging checks, retain stock ramdisk/vendor, and perform independent return-to-stock verification. Do not reuse frozen C0059 source as a writable target.

## Why this still cannot be flashed

1. Original Oct10 runtime evidence strongly favors a QGKI loaded module set (41 panic-time QGKI-only versus 0 GKI-only), and directly establishes an NFC char-device Panic. **That says nothing conclusive about the first nonblocked proprietary `modprobe -l` probe on a changed Kernel.**
2. If the first selected module is NFC, kernel `module_blacklist` can reject it with `-EPERM` and trigger OEM script's whole-directory GKI fallback; if not, later rejected NFC LKM loads can be masked by the script's bare `wait`. The real `modules.blocklist`/`modules.alias`/OEM binary listing remains unavailable.
3. The built-in guard's device behavior, OEM AVB trust/rollback policy, and complete A/B backup and restoration have not been demonstrated. User-reported unlocked bootloader / disabled AVB does not establish those independent gates.
4. No new physical Android boot, NAND write, vendor-EROFS modification, Kernel compile, or device flash occurred in this analysis.

**Recommended immediate next work:** Review the genuine OEM modprobe-first-probe and module aliases/blacklist through already held evidence if possible; otherwise preserve `UNKNOWN`, and independently design safe controlled test/rollback evidence. Do not compile and flash a draft just because its static checks pass. The `nqnfcinfo` first fault and existing OEM Oops logger remain the primary debugging target.

## Local reproduction

```sh
python3 c0061_cmdline_provenance_gate.py --self-test
python3 c0061_cmdline_provenance_gate.py --baseline-zip C0061_original_failed_5p4p302_37655937871.zip --oops-zip lisa-twrp-iter-0001_20261010-224509_boot_038e35371c97.zip --diagnostic-zip C0061_NFC_GuardedBuiltin_Diagnostic_NOT_FLASHABLE.zip --json c0061_cmdline_provenance_20261012.json
python3 c0061_embedded_cmdline_config_prepare.py --self-test
python3 c0061_embedded_cmdline_config_prepare.py --source builtin.config --output C0061_NFC_BUILTIN_EMBEDDED_BLACKLIST_UNBUILT.config --manifest c0061_embedded_blacklist_config_manifest.json --diff c0061_embedded_blacklist_config.diff
```

Never upload raw OEM Oops or the full live command line to a public repository; the scripts emit only bounded, redacted evidence.