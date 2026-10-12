# C0061 NFC cdev lifetime and source-lineage checkpoint (STATIC ONLY)

Date: 2026-10-12 (Asia/Taipei). Policy: `LOCAL_BUILD_PRIMARY + CI_AUDIT_ONLY`.
No kernel/Boot build, device test, flash, or OEM private raw log publication is asserted.

## Pinned build provenance

The previously successful NFC built-in prototype was compiled from package commit `f13410bf8cbc8f7006ea8ff6206c6441babd4320` with frozen kernel commit `6e568aabc77a06fa787baec1d9e60e4b559874a3`. The workflow at that package commit reconstructs Candidate0059, applies the ABI compatibility and Direct-302 source decisions, checks the runtime contract, and only then applies `reconstruction/scripts/candidate_0061_nfc_cdev_guard.py`.

The frozen QTI NFC source was inspected at Git blob IDs:

- `drivers/nfc/qti/nfc_common.c`: `33263e4cc623defe734f7bae29b1fbdb061f8c05`
- `drivers/nfc/qti/nfc_i2c_drv.c`: `fee83a9f9a2e89d4a93ba485225d8560e34736e6`
- `drivers/nfc/qti/nfc_common.h`: `e1984af3b097f27ffe29a86de920229934712369`

## Lifetime review (not a demonstrated UAF)

In the frozen source, `nfc_misc_remove` releases `nfc_dev->kbuf` before `device_destroy` and `cdev_del`. The I2C driver's remove path subsequently destroys a mutex and frees `nfc_dev`. The existing Guard tests `inode`/`inode->i_cdev` before `container_of` in open and prefers `filp->private_data` in release, but adds no refcount, RCU, or wait-for-active-readers teardown synchronization. The reviewed snippets therefore expose an **unproven lifetime-contract gap**, not proof of concurrent remove, use-after-free, or the original Panic cause.

## Indirect writer scope: additional static narrowing

At the **same pinned package commit**, the audited C0059 recreation helpers have explicit target paths in QCOM IPA/PAS, watchdog, MTD, reboot, procfs, scheduler, camera ownership and power files rather than `drivers/nfc/qti/`. The Candidate0059 performance manifest lists 20 files unrelated to NFC. The inherited C0058 BPF source manifest lists 19 paths and enforces a BPF-scoped allowlist; neither contains a QTI NFC path. ABI compatibility helpers similarly target MTD/SCM/timer/IRQ/qdisc. The real Direct-302 scan/apply evidence from artifact `11674503076` contains 1,760 paths and **no** `drivers/nfc/qti/` path.

The existing `candidate_0061_nfc_cdev_guard.py` has precisely two reviewed open/close replacements in `nfc_common.c`. Replaying only those replacements on the pinned frozen source predicts Git blob `b493c0536b7e407f038af01ce62aa866d4e8a45c` for `nfc_common.c`.

**Limit:** generated wrappers and the complete source-only build-stage replay have **not** been executed in this audit. No final post-materialization QTI NFC source files were uploaded by the historical Build workflow, so the **actual compiled input SHA remains UNKNOWN**. The forecast is a conditional projection, never a compiler/runtime/device PASS.

## Remaining release blockers

The original failed C0061 OEM Oops records NFC probe success around +15.57s and `nqnfcinfo -> nfc_dev_open -> mutex_lock` Panic around +41.798s. It does not attest the later built-in Boot. Actual OEM first `modprobe -l` candidate, device blocklist/alias/softdep, built-in blacklist command-line forwarding, OEM AVB trust/rollback and full A/B reversibility remain unverified. The header-only diagnostic Boot `a4918b11...331cb989c8` remains **NOT_FLASHABLE**. Candidate0059 frozen, HyperOS3.0.9 A16 baseline, EROFS, vbmeta, SELinux and thermal unchanged.

Next: run legitimate local source-only checkpoints against pinned source and package trees, compare all three QTI NFC Git blob hashes after each stage; do not rebuild an unchanged kernel or flash.
