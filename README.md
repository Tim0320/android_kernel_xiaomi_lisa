# Xiaomi lisa HyperOS Kernel Reconstruction

Target: **Xiaomi 11 Lite 5G NE / Mi 11 LE (lisa)**

Current reconstruction target:

- HyperOS: `OS2.0.16.0.UKOCNXM`
- Stock kernel: `5.4.289-qgki-g5987d69e25da`
- Platform: Qualcomm SM7325 / Yupik
- Kernel family: QGKI
- Stock vendor modules: HyperOS QGKI ABI is the compatibility oracle

## Branches

- `main` — reconstruction tooling, manifests and documentation.
- `reconstruction/5.4.289-qgki` — generated full kernel source candidate.

## Reconstruction policy

This project does not treat "build succeeds" as stock compatibility.

The reconstructed kernel must progressively match:

1. stock kernel configuration;
2. exported/imported symbols;
3. MODVERSIONS / `Module.symvers` CRCs;
4. QGKI vendor module compatibility;
5. DTB/DTBO/vendor_boot expectations;
6. real lisa boot behavior.

Only after the 5.4.289 HyperOS-compatible baseline is stable will BPF/BTF functionality be expanded.

## Source families used

The reconstruction uses multiple public source families because Xiaomi's published `lisa-r-oss` tree is older and incomplete relative to the shipping HyperOS kernel.

- Xiaomi official `lisa-r-oss`: device/reference baseline.
- MIUI-oriented Xiaomi SM8350 downstream: lisa/SM7325/QGKI vendor integration.
- Android/Qualcomm 5.4.289 history: stable/security baseline.
- Other Xiaomi kernel releases: recovery of missing Xiaomi-specific code such as `mi-memory` and `mi_cnss_statistic`.
- HyperOS stock binaries/modules: final ABI and runtime oracle.

See `reconstruction/manifest.env` and the generated branch's `reconstruction/STATUS.md` for exact provenance.

> The generated source is a reconstruction candidate until ABI and real-device validation pass.
