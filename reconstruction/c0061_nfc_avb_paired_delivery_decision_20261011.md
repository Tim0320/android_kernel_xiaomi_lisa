# C0061 paired NFC + Boot delivery: evidence-derived decision gate (2026-10-11)

Status: **BLOCKED_NOT_FLASHABLE**. No new image, flash command, signature or device deployment.

## Observed and independently classified inputs

- Persisted device C0061 panic: at boot ~41.7 seconds `nqnfcinfo` enters `nfc_dev_open [nfc_i2c]` then `mutex_lock` faults. See `c0061_twrp_new_nfc_panic_20261010_2245.md`.
- On-device stock vendor_a is EROFS; QGKI `nfc_i2c.ko` SHA256 `b37dae41aad83b6adaa1f2a16253d2a8ca931b83a534fd5fb57ceaea2424bc68` matches 71/71 kernel imported CRC, but lacks the cdev guard; GKI SHA256 `bb1e8994d0ddf0b15bd038457a850b2a8b5c7b74e1816b97dea5623c2ea5c80b` mismatches 32/68 CRC. The verified guarded build `aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b` was not installed.
- Read-only `vendor_modprobe.sh` extraction already documented in `c0061_vendor_modprobe_branch_evidence_20261010.md`: on early-init, probe the first unblocked QGKI module, then select QGKI for the rest on success or the entire GKI directory on failure. It is **not** individual-module fallback. Static loader mechanics are evidenced; actual runtime selected directory and module instance are not.
- Boot-only image built in run 37655937871 does not change vendor_a. Experimental NFC=y Boot from run 38062935154 has an embedded AVB descriptor hash mismatch; inspection-only AVB CI identifies this, not a new boot success.

## Engineering decisions: dependency- and trust-chain-first

1. **Do not repeat Boot-only flash.** It cannot deliver the already-built cdev guard and reproduces the old exposure.
2. **Do not blindly inject guarded NFC into stock vendor_a, vendor_boot or modules.load.** The loader picks whole module sets. Resolve the complete QGKI / GKI dependencies, blocklists and the selection probe first. GKI 32/68 CRC mismatch is a serious incompatibility warning, not a proven runtime branch.
3. **Do not use NFC=y to bypass module packaging before resolving collision** with OEM second-stage modprobe. The experimental Boot also fails its embedded AVB digest; fixing only its hash cannot establish trust in externally signed vbmeta.
4. **Keep candidate 0059 immutable**. Use direct 5.4.289 -> 5.4.302, SM7325/Yupik KMI and a single integrated build only after a materially changed delivery plan can pass gates.
5. **Required read-only offline inputs before choosing a partition-writing strategy:** full OEM `modules.blocklist`, `modules.load`, `modules.dep` in QGKI and GKI paths, original vendor_a/vendor_boot/boot/vbmeta partition provenance and hashes, active-slot identity and exact signed AVB descriptor/rollback requirements. Existing evidence does not establish these as complete. First exhaust archived evidence; a new TWRP collection should only be requested if a specific gap truly blocks the chosen design.
6. **Reversible delivery gate:** preserve matching stock slot backups with verified hashes, know rescue/restore operation, verify the actual module directory and whole dependency set, ABI/CRC/vermagic checks, sign/check the entire applicable AVB chain with valid authority and rollback constraints. A `verified: true` flag or file SHA alone is insufficient for trust.
7. **Fail closed:** `c0061_paired_deployment_preflight.py` reports `flash_authorized=false` always. It is an evidence consistency checker, not a signing, rollback or on-device integration verifier.

## Next concrete work

- Audit archived OEM loader inputs for full QGKI/GKI `modules.*` provenance and identify first actual probe module without guessing it from first `modules.load` entry.
- Inspect stock `vbmeta.img`, `vbmeta_system.img`, boot AVB footer/descriptors and any protected partition info; distinguish inspectable data from unavailable OEM signing keys.
- Write a typed, provenance-backed design for **either** complete vendor_a signed repack plus rollback **or** verified earlier-stage guarded module deployment. Neither path is authorized now.
- Maintain immutable run/asset hashes and return a matched, restore-capable Boot+module package only after all explicit gates pass.

Relevant upstream design documentation: https://source.android.com/docs/core/architecture/kernel/kernel-module-support ; https://source.android.com/docs/core/architecture/kernel/loadable-kernel-modules .

## 2026-10-11 repository artifact inventory audit

The current Git repository tree contains the two stock files `reconstruction/stock/stock-Image-3.09/vbmeta.img` and `vbmeta_system.img`, plus `candidate_0061_avb_descriptor_gate.py`, but **does not contain any complete OEM QGKI/GKI `modules.load`, `modules.dep`, or `modules.blocklist` file**. This is a repository-tree absence, not proof the user's earlier ZIP archives lack those files. The earlier extracted `vendor_modprobe.sh` branch evidence remains strong static evidence, but the probe module cannot be derived from a file not actually inspected. No actual branch selection is established.

The current embedded AVB gate only checks the Boot image's hash descriptor against its own bytes. The presence of stock `vbmeta.img` and `vbmeta_system.img` in Git does **not** prove the availability of private signing keys, firmware rollback-index authorization, or a signed vendor_a repack path. Treat any external AVB claim as **UNVERIFIED** until descriptor/public-key/rollback verification is independently executed against original partition images.

**Do not advance to a new kernel build or flashing** based on the available inventory. First audit existing prior TWRP archive contents for missing module metadata or archive them as private evidence. The evidence gate must distinguish (a) bytes verifiable from files, (b) signatures verified against an authorized public key, (c) OEM vendor module selector actual boot path, and (d) real slot restoration on this handset.

## 2026-10-11 Git LFS verification correction

Direct GitHub file reads show that tracked `reconstruction/stock/stock-Image-3.09/vbmeta.img` and `vbmeta_system.img` are **129-byte Git LFS pointer files**, not decoded AVB image bytes. The LFS objects identify expected payloads:

- `vbmeta.img`: 8192 bytes, SHA256 `d200dd45af1b30993764f38492c34c7afef7addccb844ad7642d1bd4558fd907`.
- `vbmeta_system.img`: 4096 bytes, SHA256 `ea61d50a1cddf84444a6bd89fbcf9c84360d4cacfb6664271ddaa23c502a2420`.

**Do not parse the 129-byte pointers as vbmeta or claim descriptors / signature / rollback are verified.** Fetch actual Git LFS payload bytes (or previously archived identical-hash partition images), check the recorded SHA256 and byte length, then use `avbtool info_image` or a verified parser offline. Even a valid descriptor parse is not OEM signing authority nor on-device rollback clearance. OEM `modules.load`, `modules.dep`, `modules.blocklist` still absent from the checked Git tree; inspect existing private ZIPs first.
