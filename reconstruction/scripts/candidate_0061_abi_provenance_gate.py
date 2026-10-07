#!/usr/bin/env python3
"""Hard-gate every Candidate0061 changed/added ABI symbol to provenance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

STABLE = {
    "xhci_dbg_trace": ("drivers/usb/host/xhci.h", ("A", "C"), "AUTO_3WAY", "CRC_DEPENDENCY"),
    "xhci_ext_cap_init": ("drivers/usb/host/xhci.h", ("A", "C"), "AUTO_3WAY", "CRC_DEPENDENCY"),
    "xhci_gen_setup": ("drivers/usb/host/xhci.c", ("A", "C"), "AUTO_3WAY", "DIRECT_OR_TYPE"),
    "xhci_resume": ("drivers/usb/host/xhci.c", ("A", "C"), "AUTO_3WAY", "DIRECT_OR_TYPE"),
    "xhci_suspend": ("drivers/usb/host/xhci.c", ("A", "C"), "AUTO_3WAY", "DIRECT_OR_TYPE"),
    "__irq_apply_affinity_hint": ("kernel/irq/manage.c", ("D",), "DIRECT", "STABLE"),
    "irq_force_affinity": ("kernel/irq/manage.c", ("D",), "DIRECT", "STABLE"),
    "irq_set_affinity": ("kernel/irq/manage.c", ("D",), "DIRECT", "STABLE"),
    "flow_rule_match_ports_range": ("net/core/flow_offload.c", ("A",), "DIRECT", "STABLE"),
    "l2cap_chan_hold": ("net/bluetooth/l2cap_core.c", ("B", "C", "D"), "DIRECT", "STABLE"),
    "page_get_link_raw": ("fs/namei.c", ("A",), "AUTO_3WAY", "STABLE"),
    "scsi_scan_host_selected": ("drivers/scsi/scsi_scan.c", ("C",), "DIRECT", "STABLE"),
    "snd_pcm_runtime_buffer_set_silence": ("sound/core/pcm_native.c", ("B",), "AUTO_3WAY", "STABLE"),
    "tasklet_setup": ("kernel/softirq.c", ("A",), "SEMANTIC_REVIEW", "REVIEWED_STABLE_ONLY"),
    "tcf_action_update_stats": ("net/sched/act_api.c", ("C",), "DIRECT", "STABLE"),
}
MIXED = {
    "qcom_scm_get_download_mode": "Candidate0059 ABI compatibility restoration",
}
EXPECTED_CHANGED = {
    "xhci_dbg_trace", "xhci_ext_cap_init", "xhci_gen_setup", "xhci_resume", "xhci_suspend",
}
EXPECTED_ADDED = (set(STABLE) - EXPECTED_CHANGED) | set(MIXED)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--abi", type=Path, required=True)
    ap.add_argument("--scan", type=Path, required=True)
    ap.add_argument("--package", type=Path, required=True)
    ap.add_argument("--json", type=Path, required=True)
    args = ap.parse_args()

    abi = json.loads(args.abi.read_text())
    scan = json.loads(args.scan.read_text())
    rows = {r["path"]: r for r in scan["files"]}
    changed = set(abi["changed"])
    added = set(abi["added"])
    removed = set(abi["removed"])
    failures = []
    proof = {}

    if removed:
        failures.append("removed symbols nonzero: " + ",".join(sorted(removed)))
    if changed != EXPECTED_CHANGED:
        failures.append(f"changed set drift: {sorted(changed)} != {sorted(EXPECTED_CHANGED)}")
    if added != EXPECTED_ADDED:
        failures.append(f"added set drift: {sorted(added)} != {sorted(EXPECTED_ADDED)}")

    for sym, (path, segments, scan_class, kind) in STABLE.items():
        if sym not in changed | added:
            failures.append(f"{sym}: missing from ABI delta")
            continue
        row = rows.get(path)
        if not row:
            failures.append(f"{sym}: scan path missing: {path}")
            continue
        got_segments = tuple(row.get("provenance_segments", []))
        got_class = row.get("class")
        if got_segments != segments:
            failures.append(f"{sym}: provenance segments {got_segments} != {segments}")
        if got_class != scan_class:
            failures.append(f"{sym}: scan class {got_class} != {scan_class}")
        proof[sym] = {
            "classification": "STABLE_ONLY",
            "path": path,
            "segments": list(segments),
            "scan_class": scan_class,
            "proof_kind": kind,
        }

    reviewed = (args.package / "reconstruction/scripts/candidate_0061_direct_302_reviewed.py").read_text()
    marker = '"kernel/softirq.c": {'
    pos = reviewed.find(marker)
    if pos < 0:
        failures.append("kernel/softirq.c reviewed decision missing")
    else:
        block = reviewed[pos:reviewed.find("\n    },", pos) + 7]
        for needle in ('"classification": "STABLE_ONLY"', '"resolution": "ADAPT"', '"A"'):
            if needle not in block:
                failures.append("tasklet_setup reviewed provenance missing " + needle)

    compat = (args.package / "reconstruction/scripts/candidate_0061_c0059_abi_compat.py").read_text()
    for sym, reason in MIXED.items():
        if sym not in added:
            failures.append(f"{sym}: expected MIXED_CONFLICT ABI addition absent")
        if "classification=MIXED_CONFLICT" not in compat or sym not in compat:
            failures.append(f"{sym}: Candidate0059 MIXED_CONFLICT compatibility proof missing")
        proof[sym] = {
            "classification": "MIXED_CONFLICT",
            "path": "reconstruction/scripts/candidate_0061_c0059_abi_compat.py",
            "segments": [],
            "scan_class": "REVIEWED_COMPAT",
            "proof_kind": reason,
        }

    delta = changed | added
    if set(proof) != delta:
        failures.append(f"provenance coverage mismatch proof={sorted(proof)} delta={sorted(delta)}")

    result = {
        "candidate": "0061",
        "changed_crc_count": len(changed),
        "added_symbol_count": len(added),
        "removed_symbol_count": len(removed),
        "provenance_covered_count": len(proof),
        "stable_symbol_count": len(STABLE),
        "mixed_conflict_symbol_count": len(MIXED),
        "provenance": proof,
        "failures": failures,
        "result": "PASS" if not failures else "FAIL",
    }
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        f"C0061_ABI_PROVENANCE_GATE={result['result']} "
        f"covered={len(proof)} stable={len(STABLE)} mixed={len(MIXED)} removed={len(removed)}"
    )
    for failure in failures:
        print("ABI_PROVENANCE_FAILURE=" + failure)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
