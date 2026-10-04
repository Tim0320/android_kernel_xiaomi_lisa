#!/usr/bin/env python3
"""Candidate0059 Stage8: audit the exact Lisa CPU-frequency control API.

This gate intentionally makes no kernel mutation.  The donor MIGT tree uses
CPUFREQ_ADJUST policy notifiers, while the pinned Lisa baseline has moved policy
limits to frequency QoS.  Passing this audit proves which API must be used by a
future bounded MIGT frequency-control port; it does not claim runtime boost.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TARGET_REF = "6e568aabc77a06fa787baec1d9e60e4b559874a3"
DONOR_REF = "LeviMarvin/android_kernel_xiaomi_alioth@e7065bc9ead4a0ca183f51101e07dd45a9d5c558"


def read(root: Path, rel: str) -> str:
    path = root / rel
    if not path.is_file():
        raise RuntimeError(f"missing required target file: {rel}")
    return path.read_text(encoding="utf-8", errors="replace")


def audit(root: Path) -> dict:
    failures: list[str] = []
    cpufreq_h = read(root, "include/linux/cpufreq.h")
    qos_h = read(root, "include/linux/pm_qos.h")
    cpufreq_c = read(root, "drivers/cpufreq/cpufreq.c")
    core_ctl_h = read(root, "include/linux/sched/core_ctl.h")

    required_cpufreq = (
        "CPUFREQ_CREATE_POLICY",
        "CPUFREQ_REMOVE_POLICY",
        "cpufreq_register_notifier",
        "cpufreq_update_policy",
        "cpufreq_cpu_get",
        "cpufreq_cpu_put",
    )
    for token in required_cpufreq:
        if token not in cpufreq_h:
            failures.append("MISSING_CPUFREQ_API:" + token)

    required_qos = (
        "FREQ_QOS_MIN",
        "FREQ_QOS_MAX",
        "FREQ_QOS_MIN_DEFAULT_VALUE",
        "FREQ_QOS_MAX_DEFAULT_VALUE",
        "freq_qos_add_request",
        "freq_qos_update_request",
        "freq_qos_remove_request",
    )
    for token in required_qos:
        if token not in qos_h:
            failures.append("MISSING_FREQ_QOS_API:" + token)

    normalized_cpufreq_h = " ".join(cpufreq_h.split())
    required_core = (
        ("struct freq_constraints constraints;", normalized_cpufreq_h),
        ("freq_qos_add_request(&policy->constraints", cpufreq_c),
        ("CPUFREQ_CREATE_POLICY, policy", cpufreq_c),
        ("CPUFREQ_REMOVE_POLICY, policy", cpufreq_c),
    )
    for token, body in required_core:
        if token not in body:
            failures.append("MISSING_CPUFREQ_CORE_SEMANTIC:" + token)

    if "core_ctl_set_boost" not in core_ctl_h:
        failures.append("MISSING_CORE_CTL_BOOST_API")

    legacy_adjust_present = "CPUFREQ_ADJUST" in cpufreq_h
    if legacy_adjust_present:
        failures.append("UNEXPECTED_LEGACY_CPUFREQ_ADJUST_PRESENT")

    report = {
        "candidate": "0059",
        "stage": "freq-control-api-audit",
        "target_ref": TARGET_REF,
        "donor_reference": DONOR_REF,
        "result": "PASS" if not failures else "FAIL",
        "failures": failures,
        "claims": {
            "legacy_cpufreq_adjust_compatible": False,
            "target_policy_events": ["CPUFREQ_CREATE_POLICY", "CPUFREQ_REMOVE_POLICY"],
            "target_frequency_qos_present": True,
            "freq_qos_min_max_supported": True,
            "core_ctl_boost_api_present": "core_ctl_set_boost" in core_ctl_h,
            "safe_next_port": "policy-scoped-freq-qos-min-max-requests",
            "raw_donor_notifier_port_allowed": False,
            "frequency_policy_ported": False,
            "boost_policy_active": False,
            "runtime_tested": False,
        },
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-root", type=Path, required=True)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    try:
        report = audit(args.source_root.resolve())
    except RuntimeError as exc:
        report = {
            "candidate": "0059",
            "stage": "freq-control-api-audit",
            "target_ref": TARGET_REF,
            "donor_reference": DONOR_REF,
            "result": "FAIL",
            "failures": [str(exc)],
        }

    if args.json:
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print("CANDIDATE0059_STAGE8_FREQ_API=" + report["result"])
    claims = report.get("claims", {})
    if claims:
        print("LEGACY_CPUFREQ_ADJUST_COMPATIBLE=false")
        print("TARGET_FREQ_QOS_PRESENT=true")
        print("CORE_CTL_BOOST_API_PRESENT=" + str(claims["core_ctl_boost_api_present"]).lower())
        print("RAW_DONOR_NOTIFIER_PORT_ALLOWED=false")
        print("FREQUENCY_POLICY_PORTED=false")
        print("BOOST_POLICY_ACTIVE=false")
        print("RUNTIME_TESTED=false")
    for item in report.get("failures", []):
        print("FAILURE=" + item)
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
