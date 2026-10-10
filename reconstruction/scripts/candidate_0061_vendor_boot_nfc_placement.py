#!/usr/bin/env python3
"""Read-only vendor_boot ramdisk NFC placement audit. Never produces a flashable artifact."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path

EXPECTED_STOCK_VENDOR_BOOT_SHA = "a94ecc2b8e53666693fd3cfc99ad07b5f24f586e85841728bf1d41333bc4b053"
GUARDED_NFC_SHA = "aa512b78538003a2be63c1c28c03eaa05ff691e54d4f8b1556b282b14c52152b"

def analyze(root: Path, load_plan: Path) -> dict:
    if not root.is_dir() or not load_plan.is_file():
        raise RuntimeError("RAMDISK_NOT_EXTRACTED_OR_LOAD_PLAN_MISSING")
    all_modules = sorted((p for p in root.rglob("*.ko") if p.is_file()), key=lambda p:str(p))
    nfc_modules = [p for p in all_modules if p.name == "nfc_i2c.ko"]
    plans = sorted((p for p in root.rglob("modules.load*") if p.is_file()), key=lambda p:str(p))
    refs = []
    for p in plans:
        for lineno, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and Path(stripped).name == "nfc_i2c.ko":
                refs.append({"file":str(p.relative_to(root)), "line":lineno})
    active = [
        x.strip() for x in load_plan.read_text(errors="replace").splitlines()
        if x.strip() and not x.strip().startswith("#")
    ]
    active_nfc = any(Path(line).name == "nfc_i2c.ko" for line in active)
    binaries = []
    for p in nfc_modules:
        blob = p.read_bytes()
        pos = blob.find(b"vermagic=")
        vm = blob[pos+9:].split(b"\x00",1)[0].decode("utf-8","replace") if pos >= 0 else ""
        binaries.append({"ramdisk_path":str(p.relative_to(root)),
                         "sha256":hashlib.sha256(blob).hexdigest(),
                         "bytes":len(blob),"vermagic":vm})
    return {
        "scope":"REPOSITORY_STOCK_VENDOR_BOOT_RAMDISK_STATIC_ONLY",
        "stock_vendor_boot_expected_sha256":EXPECTED_STOCK_VENDOR_BOOT_SHA,
        "stock_snapshot_is_live_vendor_boot_dump":False,
        "total_ramdisk_module_binaries":len(all_modules),
        "nfc_i2c_binary_count":len(nfc_modules),
        "nfc_i2c_binaries":binaries,
        "nfc_in_active_first_stage_load_plan":active_nfc,
        "nfc_in_any_ramdisk_load_plan":bool(refs),
        "nfc_load_plan_references":refs,
        "ci_guarded_nfc_sha256":GUARDED_NFC_SHA,
        "ci_guarded_nfc_in_stock_vendor_boot":any(x["sha256"]==GUARDED_NFC_SHA for x in binaries),
        "vendor_second_stage_modprobe_uses_absolute_vendor_paths":True,
        "vendor_boot_only_fixes_second_stage_nfc":False,
        "reason":"The real Android vendor_modprobe.sh selects /vendor/lib/modules or /vendor/lib/modules/5.4-gki; merely placing a .ko into vendor_boot ramdisk does NOT change those later on-partition absolute paths. A new early preload scheme would require verified init timing, identity, safety, AVB and rollback; none is demonstrated here.",
        "avb_repack_authorized":False,
        "flash_package_created":False,
        "android_device_boot_pass":False,
    }

def test():
    with tempfile.TemporaryDirectory() as t:
        p=Path(t); root=p/"root"; (root/"fragment-0/lib/modules").mkdir(parents=True)
        (root/"fragment-0/lib/modules/nfc_i2c.ko").write_bytes(b"fixture")
        (root/"fragment-0/lib/modules/modules.load").write_text("# c\nnfc_i2c.ko\nother.ko\n")
        plan=p/"active.txt";plan.write_text("nfc_i2c.ko\n")
        r=analyze(root,plan)
        assert r["nfc_i2c_binary_count"]==1
        assert r["nfc_in_active_first_stage_load_plan"]
        assert r["nfc_in_any_ramdisk_load_plan"]
        assert not r["vendor_boot_only_fixes_second_stage_nfc"]
        assert not r["flash_package_created"]
        plan.write_text("other.ko\n")
        r=analyze(root,plan)
        assert not r["nfc_in_active_first_stage_load_plan"]
    print("C0061_VENDOR_BOOT_NFC_PLACEMENT_SELF_TEST=PASS")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--root",type=Path)
    a.add_argument("--active-load",type=Path)
    a.add_argument("--json",type=Path)
    a.add_argument("--self-test",action="store_true")
    x=a.parse_args()
    if x.self_test:
        test(); return
    if not (x.root and x.active_load and x.json):
        a.error("--root, --active-load, --json are required")
    result=analyze(x.root,x.active_load)
    x.json.parent.mkdir(parents=True,exist_ok=True)
    x.json.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("C0061_VENDOR_BOOT_NFC_PLACEMENT_AUDIT=PASS")
    print("NFC_IN_STOCK_VENDOR_RAMDISK="+str(result["nfc_i2c_binary_count"]))
    print("NFC_FIRST_STAGE_LOAD_PLAN="+str(result["nfc_in_active_first_stage_load_plan"]).lower())
    print("VENDOR_BOOT_ONLY_FIXES_SECOND_STAGE_NFC=NO")
    print("READY_TO_FLASH=NO")

if __name__ == "__main__":
    main()
