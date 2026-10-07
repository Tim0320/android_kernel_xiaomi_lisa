#!/usr/bin/env python3
"""Verify Candidate0059 runtime-equivalence layers after Direct-302 materialization."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def contains(path: Path, token: str) -> bool:
    return path.is_file() and token in path.read_text(errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    k = args.source.resolve()

    checks = {
        "source_identity_5_4_302": contains(k / "Makefile", "SUBLEVEL = 302\n"),

        # Real Candidate0059 carries Candidate0046 healthy-stock watchdog
        # Kconfig semantics; Direct-302 must not erase those range/default edits.
        "watchdog_bark_default_20000": contains(k / "drivers/soc/qcom/Kconfig", "default 20000"),
        "watchdog_bark_range_11000_20000": contains(k / "drivers/soc/qcom/Kconfig", "range 11000 20000"),
        "watchdog_pet_default_15000": contains(k / "drivers/soc/qcom/Kconfig", "default 15000"),
        "watchdog_pet_range_9360_15000": contains(k / "drivers/soc/qcom/Kconfig", "range 9360 15000"),

        # Candidate0054 raw first-fault persistence inherited by real C0059.
        "raw_fault_capture": contains(k / "arch/arm64/mm/fault.c", "lisa_arm64_capture_first_fault(addr, esr, regs);"),
        "raw_fault_marker": contains(k / "arch/arm64/mm/fault.c", "LISA0054_RAW_FAULT saved=1"),
        "raw_fault_header": (k / "include/linux/lisa_fault_capture.h").is_file(),
        "raw_fault_mtd_append": contains(k / "drivers/mtd/mtdoops.c", "lisa_arm64_fault_copy(lisa_fault_text"),
        "raw_module_relocation_map": contains(k / "kernel/module.c", "LISA0054_MODULE name=%s"),

        # Candidate0046/Candidate0053 Lisa/Yupik IPA/PAS contract.
        "mtd_sync_checkpoint": contains(k / "drivers/mtd/mtdoops.c", "void lisa_mtdoops_checkpoint(const char *tag)"),
        "ipa_before_pas_checkpoint": contains(k / "drivers/soc/qcom/subsys-pil-tz.c", 'lisa_mtdoops_checkpoint("ipa_before_pas_auth_reset");'),
        "ipa_after_pas_checkpoint": contains(k / "drivers/soc/qcom/subsys-pil-tz.c", 'lisa_mtdoops_checkpoint("ipa_after_pas_auth_reset");'),
        "ipa_fw_shmbridge": contains(k / "drivers/soc/qcom/subsys-pil-tz.c", "qtee_shmbridge_register(d->lisa_ipa_fw_addr"),
        "ipa_full_region": contains(k / "drivers/soc/qcom/subsys-pil-tz.c", "LISA0053_IPA_REGION stage=mem_setup_full"),
        "ipa_metadata_retention": contains(k / "drivers/firmware/qcom_scm.c", "LISA0053_IPA_METADATA stage=after_auth_reset"),
        "yupik_ipa_region": contains(k / "arch/arm64/boot/dts/vendor/qcom/yupik.dtsi", "reg = <0x0 0x8b710000 0x0 0xa000>;"),
        "yupik_ipa_firmware": contains(k / "arch/arm64/boot/dts/vendor/qcom/yupik.dtsi", 'qcom,firmware-name = "yupik_ipa_fws";'),

        # Candidate0019->0046 early-runtime fix.
        "qxm_ipa_qos_hard_disabled": contains(k / "drivers/interconnect/qcom/yupik.c", "Lisa Candidate 0046 diagnostic: never touch inaccessible IPA QoS MMIO."),
        "qxm_ipa_qosbox_null": contains(k / "drivers/interconnect/qcom/yupik.c", ".qosbox = NULL,"),
        "qxm_ipa_runtime_marker": contains(k / "drivers/interconnect/qcom/yupik.c", "Lisa Candidate 0046: qxm_ipa QoS fully disabled"),

        # Other verified Candidate0059 inherited runtime layers.
        "proc_create_legacy_abi": contains(k / "fs/proc/generic.c", "Lisa Candidate 0050: legacy proc_create(file_operations) ABI bridge active"),
        "ufs_registry_hook": contains(k / "drivers/scsi/ufs/ufshcd.c", "set_ufs_hba_data(sdev);"),
        "ufs_registry_provider": contains(k / "drivers/misc/mi-memory/mem_interface.c", "void set_ufs_hba_data("),
        "power_compat_source": contains(k / "kernel/power/lisa_power_compat.c", "POWER_COMPAT ready=1"),
        "power_compat_linked": contains(k / "kernel/power/Makefile", "lisa_power_compat.o"),
        "camera_yupik_modular": contains(k / "techpack/camera/config/yupikcamera.conf", "export CONFIG_SPECTRA_CAMERA=m"),
        "camera_lahaina_modular": contains(k / "techpack/camera/config/lahainacamera.conf", "export CONFIG_SPECTRA_CAMERA=m"),
        "package_runtime_core": (k / "kernel/sched/pkg_core.c").is_file(),
        "migt_core": (k / "drivers/mihw/migt.c").is_file(),
    }

    failures = [name for name, ok in checks.items() if not ok]
    report = {
        "candidate": "0061",
        "gate": "post_direct_302_candidate0059_runtime_contract",
        "result": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failures": failures,
    }
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print("C0061_POST_302_C0059_RUNTIME_CONTRACT=" + report["result"])
    for name, ok in checks.items():
        print(f"RUNTIME_CONTRACT_{name}={int(ok)}")
    for name in failures:
        print("RUNTIME_CONTRACT_FAILURE=" + name)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
