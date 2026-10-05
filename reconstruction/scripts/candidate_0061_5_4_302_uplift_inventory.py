#!/usr/bin/env python3
"""Candidate0061 no-build inventory for the Lisa Linux 5.4.302 uplift."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

UP_289 = "upstream-v5.4.289"
UP_302 = "upstream-v5.4.302"
SENSITIVE = (
    "arch/arm64/",
    "include/linux/",
    "include/uapi/",
    "kernel/sched/",
    "kernel/time/",
    "kernel/bpf/",
    "net/",
    "mm/",
    "fs/",
    "security/",
    "drivers/cpufreq/",
    "drivers/thermal/",
    "drivers/scsi/ufs/",
    "drivers/firmware/qcom/",
    "drivers/soc/qcom/",
    "drivers/interconnect/qcom/",
    "drivers/gpu/",
    "techpack/display/",
    "scripts/",
    "Kbuild",
    "Makefile",
)


def sh(repo: Path, *args: str) -> str:
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return p.stdout


def files(repo: Path, a: str, b: str) -> set[str]:
    return {x for x in sh(repo, "diff", "--name-only", a, b).splitlines() if x}


def version(root: Path) -> str:
    vals = {}
    for line in (root / "Makefile").read_text(errors="replace").splitlines():
        if "=" not in line:
            continue
        k, v = [x.strip() for x in line.split("=", 1)]
        if k in {"VERSION", "PATCHLEVEL", "SUBLEVEL"}:
            vals[k] = v
    return ".".join(vals[k] for k in ("VERSION", "PATCHLEVEL", "SUBLEVEL"))


def is_sensitive(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in SENSITIVE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", type=Path, required=True)
    ap.add_argument("--donor", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, default=Path("candidate-0061-uplift-inventory.json"))
    ap.add_argument("--out-md", type=Path, default=Path("candidate-0061-uplift-inventory.md"))
    args = ap.parse_args()

    lisa_ver = version(args.kernel)
    donor_ver = version(args.donor)
    if lisa_ver != "5.4.289":
        raise SystemExit(f"Unexpected Lisa source version: {lisa_ver}")
    if donor_ver != "5.4.302":
        raise SystemExit(f"Unexpected MiYume donor version: {donor_ver}")

    stable = files(args.kernel, UP_289, UP_302)
    lisa_vendor = files(args.kernel, UP_289, "HEAD")
    overlap = stable & lisa_vendor

    donor_delta = files(args.donor, UP_302, "HEAD")
    donor_overlap = overlap & donor_delta

    sensitive_stable = {p for p in stable if is_sensitive(p)}
    sensitive_overlap = {p for p in overlap if is_sensitive(p)}
    sensitive_donor_overlap = {p for p in donor_overlap if is_sensitive(p)}

    result = {
        "candidate": "0061",
        "purpose": "Linux 5.4.289 -> 5.4.302 no-build conflict inventory",
        "lisa_version": lisa_ver,
        "donor_version": donor_ver,
        "stable_changed_files": len(stable),
        "lisa_vendor_divergence_files": len(lisa_vendor),
        "stable_x_lisa_overlap_files": len(overlap),
        "sensitive_stable_files": len(sensitive_stable),
        "sensitive_overlap_files": len(sensitive_overlap),
        "donor_modified_overlap_files": len(donor_overlap),
        "sensitive_donor_modified_overlap_files": len(sensitive_donor_overlap),
        "stable_files": sorted(stable),
        "lisa_vendor_files": sorted(lisa_vendor),
        "overlap_files": sorted(overlap),
        "sensitive_overlap": sorted(sensitive_overlap),
        "donor_modified_overlap": sorted(donor_overlap),
        "sensitive_donor_modified_overlap": sorted(sensitive_donor_overlap),
        "policy": {
            "stable_source_of_truth": True,
            "miyume_is_reference_only": True,
            "whole_file_donor_copy_forbidden": True,
            "sublevel_only_bump_forbidden": True,
        },
    }
    args.out_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    lines = [
        "# Candidate0061 5.4.302 uplift inventory",
        "",
        f"- Lisa source version: {lisa_ver}",
        f"- MiYume donor version: {donor_ver}",
        f"- Official stable changed files: {len(stable)}",
        f"- Lisa-vs-upstream-5.4.289 divergence files: {len(lisa_vendor)}",
        f"- Stable/Lisa overlap files: {len(overlap)}",
        f"- Sensitive overlap files: {len(sensitive_overlap)}",
        f"- Overlap files also modified by MiYume vs upstream 5.4.302: {len(donor_overlap)}",
        "",
        "## Sensitive conflict-risk files",
        "",
    ]
    lines += [f"- {p}" for p in sorted(sensitive_overlap)] or ["- none"]
    lines += ["", "## Sensitive files where MiYume may provide an adaptation reference", ""]
    lines += [f"- {p}" for p in sorted(sensitive_donor_overlap)] or ["- none"]
    lines += [
        "",
        "MiYume is reference-only. Resolve official stable changes semantically in Lisa; do not replace whole vendor files.",
        "",
    ]
    args.out_md.write_text("\n".join(lines))
    print("LISA_CANDIDATE_0061_UPLIFT_INVENTORY=PASS")
    print(f"stable_changed_files={len(stable)}")
    print(f"stable_x_lisa_overlap_files={len(overlap)}")
    print(f"sensitive_overlap_files={len(sensitive_overlap)}")
    print(f"donor_modified_overlap_files={len(donor_overlap)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
