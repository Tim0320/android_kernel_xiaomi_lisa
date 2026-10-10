# Candidate0061: vendor module fallback, dependency graph and masked failures

Date: 2026-10-10. **Read-only offline analysis; not an Android boot test.** Source manifests from previously uploaded `lisa_nfc_module_configs_20261010-212249.zip`, ZIP SHA256 `3a8717640a28b8facbd46e59bf796a577b462bbce1cc7d521d768e7218b6ac0b`. Loader behavior from privately supplied `vendor_modprobe.sh`; it has an OEM proprietary header, so do **not** reproduce its verbatim contents in this public report.

## Confirmed graph audit

New reusable parser `reconstruction/scripts/candidate_0061_vendor_manifest_graph.py` (commit `3e4c3c9`) was executed locally with **both actual read-only vendor manifest sets**. The checker verifies `modules.load` name uniqueness, `modules.dep` cross-references, unresolved dependencies, cycles and high fan-in, without uploading private OEM manifests. A fixture-based regression/self-test also checks a valid dependency, a missing dependency, and a dependency cycle. CI run `38058408963` **SUCCESS** validates the script's Python syntax and its fixture self-test alongside the existing C0061 NFC CRC preflight.

| Measured static property | QGKI path `/vendor/lib/modules` | GKI `/vendor/lib/modules/5.4-gki` |
| --- | ---: | ---: |
| `modules.load` names | 107 | 227 |
| `modules.dep` entries | 107 | 227 |
| Direct dependency edges | 211 | 741 |
| Missing/unresolved dependency edges | 0 | 0 |
| Dependency cycles | 0 | 0 |
| Highest direct fan-in | `q6_pdr_dlkm.ko`, 20 | `qmi_helpers.ko`, 76 |
| Other high direct fan-in | `snd_event_dlkm.ko`, 19; `q6_notifier_dlkm.ko`, 19 | `subsystem_restart.ko`, 68; `service-locator.ko`, 45 |
| `nfc_i2c.ko` included in `modules.load` | yes | yes |
| `llcc-yupik.ko` included in `modules.load` | no | yes |

63 module names appear in both `modules.load` files; 44 appear only in QGKI and 164 only in GKI. Dependency graph *syntax* and internal path closure do not establish that any .ko is compatible with Candidate0061 5.4.302, nor that Android loaded it. In particular, the GKI NFC module imported CRCs **32/68 mismatch** while the QGKI NFC module **71/71 match**, from the separate actual-ELF CRC evidence `reconstruction/c0061_stock_nfc_crc_comparison_20261010.md`.

## More precise interpretation of the Android vendor loader

The observed OEM loader executes early-init and first tries one non-blocklisted QGKI module; it selects the GKI directory for subsequent attempts **only if that initial QGKI module load fails**. It does **not** retry individual later module load failures in the other directory.

- `modprobe -l` is **not** guaranteed to be ordered as `modules.load`. AOSP `ListModules()` enumerates the internal `module_deps_` hash map, whereas `modules.load` has a different `LoadListedModules` path. The actual Xiaomi vendor binary's enumeration order and selected first module are unknown. AOSP references for mechanism only: https://android.googlesource.com/platform/system/core/+/android16-qpr2-release/libmodprobe/libmodprobe.cpp and https://android.googlesource.com/platform/system/core/+/android16-qpr2-release/toolbox/modprobe.cpp .
- Both `modules.blocklist` files were **not retrieved**: `adb pull` errors do not alone establish they are absent on the device. Only *if* the QGKI `modules.blocklist` is absent does the source script's `cat ... | grep` test likely treat the first enumerated candidate as not blocklisted; no definitive initial module name follows from the captured manifests.
- The script starts most of the later module loads as background children and ends with a bare `wait`. POSIX `wait` with **no PID operands** normally exits 0 after waiting for all children, **even if some children exit nonzero**. Verified with host `bash` and `dash` tests `(exit 7) & wait`, each returning 0. Android's exact `/vendor/bin/sh` was not executed in that local test. Sources: https://www.man7.org/linux/man-pages/man1/wait.1p.html . Therefore an init-visible successful completion of this vendor script would not prove each background `modprobe` succeeded.
- The loader also intentionally skips a few WIFI/fragmentize module-name cases; `modules.load` manifest membership does not prove actual runtime loading.

## Current gate and safe next actions

1. **Conditionally severe branch:** if the first QGKI test fails and the script switches the entire remaining module set to GKI, an ABI-mismatched NFC module is among the candidates. A high-fan-in module mismatch could affect many downstream modules. This is **not** proof that the fallback happened, that NFC caused the system-stage reboot, or that each listed GKI module would be loaded. No new current-boot first-fault was provided.
2. **No blind partition changes:** both vendor locations are EROFS read-only, with AVB implications. Do not copy a standalone 5.4.302 `nfc_i2c.ko` into the vendor partition, force loading, relax SELinux/thermal or rebuild an unchanged boot to hide the uncertainty.
3. **Next autonomous task:** review Candidate0061's boot-module layout and its build's exported symbols, compare specific first-probe/dependency risks against known Lisa kernel source, identify a reversible test design. If a consequential missing fact truly needs fresh device evidence, request only a read-only, targeted TWRP/ADB capture starting PowerShell in `D:\1.ROM_Prot\lisa\pull_log`. Do not repeat unchanged old Oops/Logdump, NFC CRC or manifests.
4. **Reporting gates:** latest Action URL if newly run, else `無`; mark `boot打包可準備測試` **only** for a fresh validated boot.img-producing build artifact. This run created no new kernel or boot.

**Classification:** `VENDOR_MANIFEST_GRAPH_PASS`, `FIRST_PROBE_BRANCH_UNVERIFIED`, `GKI_NFC_ABI_MISMATCH_IF_SELECTED`, `DEVICE_FIRST_FAULT_UNVERIFIED`.
