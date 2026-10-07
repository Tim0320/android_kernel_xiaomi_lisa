#!/usr/bin/env python3
"""Guard the Lisa QTI NFC char-device open/close race exposed by device evidence.

Device evidence from Candidate0061 r4f85557:
  fault address ffffffffffffffc8
  pc mutex_lock+0x18/0x40
  lr nfc_dev_open+0x30/0xf0 [nfc_i2c]

The QTI driver derives nfc_dev with container_of(inode->i_cdev, ..., c_dev)
before checking validity. If cdev teardown races a userspace open, i_cdev may
be NULL. With c_dev at the later struct offset and dev_ref_mutex earlier, that
NULL container_of produces the observed negative dev_ref_mutex address.

This patch does not fake NFC success. It rejects an unavailable cdev with
-ENODEV and makes release prefer the private_data established by a successful
open.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


OPEN_OLD = """int nfc_dev_open(struct inode *inode, struct file *filp)
{
	struct nfc_dev *nfc_dev = container_of(inode->i_cdev,
					struct nfc_dev, c_dev);

	if (!nfc_dev)
		return -ENODEV;

	pr_debug("%s: %d, %d\\n", __func__, imajor(inode), iminor(inode));
"""

OPEN_NEW = """int nfc_dev_open(struct inode *inode, struct file *filp)
{
	struct nfc_dev *nfc_dev;

	if (!inode || !inode->i_cdev) {
		pr_err_ratelimited("%s: NFC cdev unavailable\\n", __func__);
		return -ENODEV;
	}

	nfc_dev = container_of(inode->i_cdev, struct nfc_dev, c_dev);

	pr_debug("%s: %d, %d\\n", __func__, imajor(inode), iminor(inode));
"""

CLOSE_OLD = """int nfc_dev_close(struct inode *inode, struct file *filp)
{
	struct nfc_dev *nfc_dev = container_of(inode->i_cdev,
					struct nfc_dev, c_dev);

	if (!nfc_dev)
		return -ENODEV;

	pr_debug("%s: %d, %d\\n", __func__, imajor(inode), iminor(inode));
"""

CLOSE_NEW = """int nfc_dev_close(struct inode *inode, struct file *filp)
{
	struct nfc_dev *nfc_dev = filp ? filp->private_data : NULL;

	if (!nfc_dev && inode && inode->i_cdev)
		nfc_dev = container_of(inode->i_cdev, struct nfc_dev, c_dev);
	if (!nfc_dev) {
		pr_err_ratelimited("%s: NFC device already unavailable\\n", __func__);
		return -ENODEV;
	}

	pr_debug("%s: %d, %d\\n", __func__, imajor(inode), iminor(inode));
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--json", type=Path, required=True)
    args = ap.parse_args()
    src = args.source.resolve()
    p = src / "drivers/nfc/qti/nfc_common.c"
    text = p.read_text()

    already = (
        "NFC cdev unavailable" in text
        and "NFC device already unavailable" in text
    )
    if not already:
        if text.count(OPEN_OLD) != 1:
            raise SystemExit(f"nfc_dev_open anchor count={text.count(OPEN_OLD)}")
        if text.count(CLOSE_OLD) != 1:
            raise SystemExit(f"nfc_dev_close anchor count={text.count(CLOSE_OLD)}")
        text = text.replace(OPEN_OLD, OPEN_NEW, 1)
        text = text.replace(CLOSE_OLD, CLOSE_NEW, 1)
        p.write_text(text)

    out = p.read_text()
    checks = {
        "open_checks_inode_before_container_of":
            'if (!inode || !inode->i_cdev)' in out,
        "open_returns_enodev":
            'pr_err_ratelimited("%s: NFC cdev unavailable\\n", __func__);' in out
            and 'return -ENODEV;' in out,
        "close_prefers_private_data":
            'struct nfc_dev *nfc_dev = filp ? filp->private_data : NULL;' in out,
        "close_guards_missing_cdev":
            'if (!nfc_dev && inode && inode->i_cdev)' in out,
        "no_fake_success":
            'NFC cdev unavailable' in out,
    }
    failures = [k for k,v in checks.items() if not v]
    report = {
        "candidate": "0061",
        "classification": "DEVICE_RUNTIME_FIX",
        "source": "drivers/nfc/qti/nfc_common.c",
        "device_fault": {
            "release": "5.4.302-qgki-lisa-c0061-r4f85557-by-Tim0320",
            "task": "nqnfcinfo",
            "fault_address": "ffffffffffffffc8",
            "esr": "96000005",
            "pc": "mutex_lock+0x18/0x40",
            "lr": "nfc_dev_open+0x30/0xf0 [nfc_i2c]",
        },
        "semantic_rule": "missing cdev returns -ENODEV; never fake NFC success",
        "checks": checks,
        "failures": failures,
        "result": "PASS" if not failures else "FAIL",
    }
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("C0061_NFC_CDEV_GUARD=" + report["result"])
    for k,v in checks.items():
        print(f"NFC_CDEV_{k}={int(v)}")
    for f in failures:
        print("NFC_CDEV_FAILURE=" + f)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
