#!/usr/bin/env python3
"""Offline, read-only triage of existing Lisa OEM Oops captures.

This only reads local files, writes a local summary and never uploads logs or
contacts devices. OEM Oops may contain records from several different boots.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def classify(data):
    checks = {
        "kernel_panic": b"Kernel panic - not syncing:" in data,
        "arm64_oops": b"Internal error: Oops:" in data,
        "nfc_dev_open": b"nfc_dev_open" in data,
        "nqnfcinfo": re.search(rb"Comm:\s*nqnfcinfo\b", data) is not None,
        "module_nfc_present": re.search(
            rb"Modules linked in:[^\r\n]*\bnfc_i2c\b", data) is not None,
        "lisa_raw_fault": b"LISA0054_RAW_FAULT" in data,
        "emergency_restart": b"emergency_restart" in data,
        "init_activity": b"init:" in data,
        "framework_hint": b"system_server" in data or b"zygote" in data,
        "boot_completed_hint": re.search(
            rb"sys\.boot_completed\s*[=:]\s*1\b", data) is not None,
    }
    first_fault = "UNKNOWN"
    if checks["kernel_panic"] and checks["nfc_dev_open"] and checks["nqnfcinfo"]:
        first_fault = "RECORDED_NFC_OPEN_KERNEL_PANIC"
    elif checks["kernel_panic"]:
        first_fault = "KERNEL_PANIC_CAUSE_UNCLASSIFIED"
    stage = "UNKNOWN"
    if checks["nqnfcinfo"]:
        stage = "ANDROID_USERSPACE_REACHED_FRAMEWORK_UNKNOWN"
    elif checks["boot_completed_hint"]:
        stage = "BOOT_COMPLETE_TOKEN_PRESENT_NOT_RUNTIME_ATTESTED"
    elif checks["init_activity"]:
        stage = "INIT_ACTIVITY_PRESENT_NOT_COMPLETION"
    releases = sorted(set(
        m.decode("ascii", "replace").strip()
        for m in re.findall(rb"5\.4\.302-qgki-lisa-c0061-[A-Za-z0-9-]{1,40}", data)
    ))[:10]
    return checks, stage, first_fault, releases

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oops", type=Path, required=True)
    ap.add_argument("--previous", type=Path)
    ap.add_argument("--json", type=Path, required=True)
    args = ap.parse_args()
    if not args.oops.is_file() or not 0 < args.oops.stat().st_size <= 128*1024*1024:
        raise SystemExit("OEM Oops file unavailable or outside bounded size")
    data = args.oops.read_bytes()
    checks, stage, fault, releases = classify(data)
    current = sha256(data)
    previous = sha256(args.previous.read_bytes()) if args.previous else None
    freshness = ("NO_PRIOR_FILE" if previous is None else
                 "SAME_CAPTURE_BYTES" if current == previous else
                 "BYTES_CHANGED_TIME_UNPROVEN")
    result = {
        "sha256": current, "bytes": len(data),
        "prior_sha256": previous, "freshness": freshness,
        "stage": stage, "fault": fault,
        "checks": checks, "kernel_releases": releases,
        "actual_qgki_gki_loader_branch": "UNKNOWN",
        "note": "Ring-buffer entries can be stale; do not infer a crash time from TWRP ZIP timestamp",
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n")
    print("C0061_OEM_OOPS_TRIAGE=PASS")
    print("C0061_STAGE="+stage)
    print("C0061_FAULT="+fault)
    print("C0061_FRESHNESS="+freshness)

if __name__ == "__main__":
    main()
