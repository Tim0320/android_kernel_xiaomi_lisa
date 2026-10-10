# Candidate0061 5.4.302 xHCI CRC exposure versus GKI fallback USB module candidates

Date: 2026-10-10 (Asia/Taipei). **Offline source/build/device-manifest evidence only. NOT an Android boot root-cause finding.**

## Actual source and independent build provenance

- Full successful integrated build [GitHub Actions #37655937871](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/37655937871), original evidence artifact `11500359180` containing the **same-run** reconstructed Candidate0059 control `Module.symvers` and config, and candidate0061 Direct-302 5.4.302 target `Module.symvers` and config.
- Control `Module.symvers`: 14,423 exports; target: 14,434. **Removed=0, added=11, existing-CRC-changed=5.** All five changed exports belong to built-in USB/xHCI functions and are `vmlinux` / `EXPORT_SYMBOL_GPL` in both builds.

| Imported symbol name | C0059 control CRC | C0061 target CRC |
| --- | --- | --- |
| `xhci_dbg_trace` | `0x3dc34dfe` | `0xa1f8fad0` |
| `xhci_ext_cap_init` | `0x57ed4b9d` | `0x8ca6136b` |
| `xhci_gen_setup` | `0x2033f1e5` | `0x75ff0fe3` |
| `xhci_resume` | `0xaf0bba47` | `0xc8b2f4a9` |
| `xhci_suspend` | `0x7c5c2b95` | `0xa065eb97` |

The actual integrated kernel config comparison shows **only** `CONFIG_LOCALVERSION` and `CONFIG_SURFACE_PLATFORMS` drift; `CONFIG_USB_XHCI_HCD`, `CONFIG_USB_XHCI_PCI`, `CONFIG_USB_XHCI_PLATFORM`, `CONFIG_USB_DWC3`, `CONFIG_USB_DWC3_MSM`, and `CONFIG_MODVERSIONS` are `y` in BOTH C0059 and C0061 builds. Thus the built-in USB configuration itself was not newly enabled by Direct-302. These CRC changes constitute potential backwards module ABI incompatibility **only for OEM modules that actually import these specific five symbols**; such imports have not been demonstrated.

- Original authentic TWRP EROFS `vendor_a` capture `lisa_nfc_module_configs_20261010-212249.zip` (previously verified ZIP SHA256 `3a8717640a28b8facbd46e59bf796a577b462bbce1cc7d521d768e7218b6ac0b`): QGKI `/vendor/lib/modules/modules.load` has 107 names, GKI `/vendor/lib/modules/5.4-gki/modules.load` has 227. Seven relevant USB `.ko` names appear in GKI but not QGKI: `xhci-hcd.ko`, `xhci-plat-hcd.ko`, `xhci-pci.ko`, `dwc3.ko`, `dwc3-msm.ko`, `dwc3-haps.ko`, `dwc3-of-simple.ko`. Their corresponding config entries are `=y` for the actual rebuilt kernel on both versions. This is a **conditional built-in/module duplication risk if the Android vendor loader falls back to the GKI directory**, NOT proof any of the seven modules were actually attempted, accepted, or caused a reboot. Duplicated driver coverage pre-existed in C0059 so cannot be assigned to the 5.4.302 stable uplift by itself.
- Both `modules.blocklist` pulls failed; this does not prove absence. Vendor `modprobe -l` first candidate is not established from `modules.load` order; Android runtime QGKI→GKI fallback unobserved.

## Independent CI gate and failure-to-fix record

- Offline xHCI audit code `reconstruction/scripts/candidate_0061_xhci_abi_exposure.py`, introduced `aa98584d554af29e7ba352416968f22c93583389`.
- New evidence-only workflow `.github/workflows/verify-lisa-candidate-0061-xhci-abi.yml` at `81c8bd7`; first Action [#38059901420](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38059901420) **FAILED** at a deliberately mutated export CRC check because the initial script only pinned the *set* of five changed names and not their exact CRC values. This was a checker defect; the authentic positive evidence test had passed.
- Fixed source `645f3e942c1fec67c9485a9e0e7aabe79baed457` now pins the five observed `(control_crc,target_crc)` pairs and fails if either is changed. Subsequent Action [#38059953730](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38059953730) **SUCCESS**, including actual same-run 14,423→14,434 export/config check and a working negative-control mutation test. Downloaded artifact `11672428058`, checked the machine-readable JSON: `result=PASS`, `failures=[]`, `changed_crc_export_count=5`, `removed_export_count=0`, `added_export_count=11`, `device_boot_pass=false`. This workflow **did not build a new kernel or boot.img** and is **not flashable**.

Official mechanism: https://www.kernel.org/doc/html/latest/kbuild/modules.html : `CONFIG_MODVERSIONS` compares imported symbol CRC with target exports, not merely kernel release number. This source explains potential ABI rejection mechanisms, not what actually happened on this Lisa boot.

## Triage and next evidence gates

1. Do not infer a system reboot cause from the five xHCI CRC changes without proving that an actual stock Vendor `.ko` imports them and Android attempted to load it. Do not reconfigure xHCI/DWC3 y→m blindly; both builds already had the core features built in.
2. Prioritize a **non-destructive**, rollback-conscious examination of the real Xiaomi vendor loader's initial QGKI candidate, GKI whole-directory fallback, and exact OEM module consumer imported CRC. The GKI `nfc_i2c.ko` has 32/68 CRC mismatches, while QGKI `nfc_i2c.ko` has 71/71 agreement; neither test alone proves actual loader branch or first fault.
3. If new physical data becomes essential, request targeted TWRP/ADB logs from `Set-Location "D:\1.ROM_Prot\lisa\pull_log"` using the user's fixed workdir; do not repeat previously unchanged oops/logdump or unchanged boot flash. Avoid publishing proprietary OEM `.ko` in public GitHub Actions.
4. Preserve frozen C0059 control, Lisa platform IDs, SELinux/thermal security, Vendor EROFS/AVB and recovery rollback ability; no blind USB or NFC changes.

**Status:** `XHCI_COMPILED_ABI_DRIFT_PROVEN`; `GKI_USB_BUILTIN_OVERLAP_CONDITIONAL`; `STOCK_OEM_XHCI_IMPORTERS_UNVERIFIED`; `ACTUAL_GKI_FALLBACK_UNVERIFIED`; `ANDROID_CONTEMPORANEOUS_FIRST_FAULT_UNVERIFIED`. New Kernel Build: **NO**. New Boot package: **NO**.
