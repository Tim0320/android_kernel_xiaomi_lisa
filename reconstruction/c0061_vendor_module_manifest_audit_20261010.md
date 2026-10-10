# Candidate0061 vendor NFC module manifest audit — 2026-10-10

## Source provenance

Uploaded ZIP: `lisa_nfc_module_configs_20261010-212249.zip` (SHA256 `3a8717640a28b8facbd46e59bf796a577b462bbce1cc7d521d768e7218b6ac0b`), gathered from real Lisa Android `vendor_a` EROFS mounted read-only in TWRP. The ZIP has five files: two `modules.load`, two `modules.dep`, and a `missing.txt`. Both `modules.blocklist` pulls failed; their absence from the ZIP is **not absolute proof** the files do not exist on the device. No kernel module ELF files or Android runtime log are included.

## Compared manifest statistics

| Check | `/vendor/lib/modules` (QGKI) | `/vendor/lib/modules/5.4-gki` (GKI) |
| --- | --- | --- |
| `modules.load` names | 107 (107 unique) | 227 (227 unique) |
| `modules.dep` entries | 107 | 227 |
| `nfc_i2c.ko` listed in load file | yes, line 66 | yes, line 139 |
| `nfc_i2c.ko` hard dependencies in dep | none listed | none listed |
| Names in load absent from dep | 0 | 0 |
| Names in dep absent from load | 0 | 0 |
| Dependency edges | 211 | 741 |
| Dependency references missing from that directory's dep entries | 0 | 0 |
| `modules.blocklist` pull | failed / not included | failed / not included |

The load lists share 63 names; QGKI-only names: 44, GKI-only: 164. This is a substantial change in the candidate **whole-directory module set**, not a single NFC file. Name-level dependency closure is clean, but does **not** establish kernel symbol CRC/KMI compatibility, module byte integrity, actual modprobe results or Android stable boot.

**Important:** The vendor `vendor_modprobe.sh` script obtains an enumeration from `/vendor/bin/modprobe -d DIR -l` and tests the first nonblocklisted module, not necessarily the first line of `modules.load`. Do NOT assert that `xc4000.ko` or `llcc-yupik.ko` was necessarily the first Android probe just because it starts `modules.load`; the actual device modprobe list order has not been read. Its fallback is **whole directory after this first probe** only. Both static directories have 5.4.289 `nfc_i2c.ko` while guarded C0061 output `aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b` from static CI run 37655937871 remains absent from inspected Android vendor files.

If the two blocklist files truly are missing, the proprietary vendor script's `cat modules.blocklist | grep <module>` test may return a nonzero pipeline status immediately, thus selecting the first listed candidate rather than filtering exclusions. This is a conditional hypothesis, **not verified TWRP file existence or actual Android branch selection**. Need a targeted `ls` or equivalent read-only existence check only if it affects deployment decisions.

## Safe next engineering steps before another device request

1. Examine AOSP `modprobe` / libmodprobe behavior for list enumeration, missing blocklist handling and kernel symbol/ABI rejection; distinguish device specific vendor binary from generic AOSP implementation.
2. Static review the two complete module sets and root dependencies, prioritize essential boot drivers and compatibility of the 5.4.302 kernel; do not assume `nfc_i2c` alone is causal.
3. Verify a rollback-capable kernel-plus-module deployment path and impact on EROFS/AVB before any user flash. NFC inspection-only artifact `11634242690` is not flashable.
4. If decisive device evidence is still needed, collect **only** the missing blocklist existence status and live Android modprobe/kernel errors if Android ADB=device is available. Do not repeat previously unchanged Oops/Logdump or reflash identical boot.

## User standard path and reporting

All future Windows PowerShell log gathering commands **must begin**:
`Set-Location "D:\1.ROM_Prot\lisa\pull_log"`.
Use this directory as the default for downloaded scripts, log folders, and ZIP output; create missing directories, avoid silent writes elsewhere. If a script has its own implicit output path, pass its explicit `-OutputRoot` to ensure alignment.

Always report `最新 Action 網址：<verified new Actions URL>` or `最新 Action 網址：無`, and whether new Kernel Build or boot.img exists. Only tag an Action `boot打包可準備測試` with a verified **new** gate-passing boot.img artifact suitable to prepare a test.

Relevant upstream comparison (mechanisms, not proof of Lisa boot's cause): https://android.googlesource.com/platform/system/core/+/d5e026e1a/toolbox/modprobe.cpp and https://android.googlesource.com/platform/system/core/+/refs/tags/android-11.0.0_r1/libmodprobe/libmodprobe.cpp .
