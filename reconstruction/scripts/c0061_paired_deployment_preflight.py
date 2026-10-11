#!/usr/bin/env python3
"""Read-only C0061 Boot/NFC deployment evidence gate. Never flashes or signs images."""
import argparse
import hashlib
import json
import pathlib
import sys

REQUIRED_PARTITIONS = ("boot", "vendor_boot", "vbmeta", "vendor")
REQUIRED_EVIDENCE = ("external_vbmeta_verified", "rollback_index_verified",
                     "stock_backup_sha_verified", "slot_rollback_verified",
                     "vendor_loader_path_verified", "nfc_runtime_conflict_resolved",
                     "abi_kmi_verified", "packaging_verified")

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def check(manifest):
    errors = []
    if manifest.get("device") != "lisa" or manifest.get("os") != "HyperOS 3.0.9 / Android 16":
        errors.append("DEVICE_OR_BASELINE_MISMATCH")
    if manifest.get("kernel") != "5.4.302":
        errors.append("KERNEL_VERSION_MISMATCH")
    slot = manifest.get("active_slot")
    if slot not in ("_a", "_b"):
        errors.append("ACTIVE_SLOT_UNKNOWN")
    partitions = manifest.get("partitions", {})
    for name in REQUIRED_PARTITIONS:
        record = partitions.get(name, {})
        if not isinstance(record, dict) or record.get("slot") != slot:
            errors.append("PARTITION_SLOT_UNVERIFIED:" + name)
            continue
        path = pathlib.Path(record.get("backup_path") or "/nonexistent")
        digest = record.get("backup_sha256", "")
        if not path.is_file() or len(digest) != 64 or sha256(path) != digest.lower():
            errors.append("BACKUP_HASH_UNVERIFIED:" + name)
    boot = manifest.get("candidate_boot", {})
    path = pathlib.Path(boot.get("path") or "/nonexistent")
    digest = boot.get("sha256", "")
    if not path.is_file() or len(digest) != 64 or sha256(path) != digest.lower():
        errors.append("CANDIDATE_BOOT_HASH_UNVERIFIED")
    module = manifest.get("guarded_nfc_module", {})
    module_path = pathlib.Path(module.get("path") or "/nonexistent")
    module_digest = module.get("sha256", "")
    if not module_path.is_file() or len(module_digest) != 64 or sha256(module_path) != module_digest.lower():
        errors.append("GUARDED_NFC_HASH_UNVERIFIED")
    for field in REQUIRED_EVIDENCE:
        if manifest.get(field) is not True:
            errors.append("EVIDENCE_NOT_VERIFIED:" + field)
    return {"status": "BLOCKED_NOT_FLASHABLE" if errors else "STATIC_PREFLIGHT_PASS_DEVICE_UNVERIFIED",
            "errors": errors, "flash_authorized": False}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=pathlib.Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", type=pathlib.Path)
    a = parser.parse_args()
    if a.self_test:
        result = check({})
        assert result["status"] == "BLOCKED_NOT_FLASHABLE"
        assert not result["flash_authorized"]
        print("FAIL_CLOSED_SELF_TEST=PASS")
        return 0
    if a.manifest is None:
        parser.error("--manifest required unless --self-test")
    result = check(json.loads(a.manifest.read_text()))
    output = json.dumps(result, indent=2, ensure_ascii=False)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(output + "\n")
    print(output)
    return 2 if result["errors"] else 0

if __name__ == "__main__":
    sys.exit(main())
