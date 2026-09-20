# Xiaomi lisa HyperOS kernel reconstruction

Target binary:
- ROM: `OS2.0.16.0.UKOCNXM`
- Kernel: `5.4.289-qgki-g5987d69e25da`
- Device: `lisa`
- SoC: `SM7325 / YUPIK`

Source construction:
- MIUI device baseline: `https://github.com/EndCredits/android_kernel_xiaomi_sm8350-miui.git @ ASB-2024-10-05`
- Android/Qualcomm 5.4.289 merge: `https://github.com/LineageOS/android_kernel_xiaomi_sm8350.git @ b9715311a2280e71f68ef859804c1338296c6dbe`
- Xiaomi mi-memory donor: `https://github.com/popoASM/veux.git @ main`
- Xiaomi CNSS statistics donor: `https://github.com/Pzqqt/android_kernel_xiaomi_marble.git @ melt-rebase`
- Historical device reference: `https://github.com/MiCode/Xiaomi_Kernel_OpenSource.git @ lisa-r-oss`

## Validation state

This branch is a **reconstruction candidate**, not yet a claimed stock-equivalent kernel.

Required before stock-equivalent status:
1. Build with the stock-compatible clang/QGKI configuration.
2. Compare `Module.symvers` CRCs with HyperOS stock modules.
3. Validate all stock QGKI vendor modules load without unknown-symbol/version failures.
4. Validate DTB/DTBO/vendor_boot compatibility.
5. Boot-test on lisa and inspect early boot/module logs.
6. Only after the stock-compatible baseline works, extend BPF/BTF features.
