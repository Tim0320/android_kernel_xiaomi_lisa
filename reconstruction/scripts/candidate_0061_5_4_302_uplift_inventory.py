#!/usr/bin/env python3
"""Candidate0061 no-build inventory for the Lisa Linux 5.4.302 uplift."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

UP_289 = "upstream-v5.4.289"
UP_302 = "upstream-v5.4.302"
BATCH_A_STEPS = (
    ("5.4.289", "5.4.290", "upstream-v5.4.289", "upstream-v5.4.290"),
    ("5.4.290", "5.4.291", "upstream-v5.4.290", "upstream-v5.4.291"),
    ("5.4.291", "5.4.292", "upstream-v5.4.291", "upstream-v5.4.292"),
)
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

C0060_CORE_SURFACE = (
    "kernel/bpf/Makefile",
    "kernel/bpf/ringbuf.c",
    "kernel/bpf/btf.c",
    "kernel/bpf/bpf_iter.c",
    "kernel/bpf/map_iter.c",
    "kernel/bpf/task_iter.c",
    "kernel/bpf/prog_iter.c",
    "kernel/bpf/trampoline.c",
    "kernel/bpf/bpf_struct_ops.c",
    "kernel/bpf/bpf_lsm.c",
    "kernel/bpf/bpf_local_storage.c",
    "kernel/bpf/bpf_inode_storage.c",
    "kernel/bpf/syscall.c",
    "kernel/bpf/verifier.c",
    "kernel/bpf/helpers.c",
    "include/linux/bpf.h",
    "include/linux/bpf_types.h",
    "include/uapi/linux/bpf.h",
    "net/core/filter.c",
    "arch/arm64/include/asm/unistd32.h",
    "fs/file.c",
    "include/linux/fdtable.h",
    "include/uapi/asm-generic/unistd.h",
    "include/uapi/linux/close_range.h",
    "kernel/sys.c",
    "security/selinux/include/classmap.h",
    "include/uapi/linux/capability.h",
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

    c0060_surface = set(C0060_CORE_SURFACE)
    c0060_stable_overlap = c0060_surface & stable
    c0060_lisa_vendor_overlap = c0060_surface & lisa_vendor
    c0060_donor_delta = c0060_surface & donor_delta
    c0060_three_way_overlap = c0060_surface & stable & donor_delta

    sensitive_stable = {p for p in stable if is_sensitive(p)}
    sensitive_overlap = {p for p in overlap if is_sensitive(p)}
    sensitive_donor_overlap = {p for p in donor_overlap if is_sensitive(p)}

    batch_a_steps = []
    for from_ver, to_ver, from_ref, to_ref in BATCH_A_STEPS:
        step_stable = files(args.kernel, from_ref, to_ref)
        step_overlap = step_stable & lisa_vendor
        step_sensitive = {p for p in step_overlap if is_sensitive(p)}
        step_donor_overlap = step_overlap & donor_delta
        batch_a_steps.append({
            "from": from_ver,
            "to": to_ver,
            "changed_files": len(step_stable),
            "lisa_vendor_overlap_files": len(step_overlap),
            "sensitive_overlap_files": len(step_sensitive),
            "donor_modified_overlap_files": len(step_donor_overlap),
            "changed_file_list": sorted(step_stable),
            "lisa_vendor_overlap_list": sorted(step_overlap),
            "sensitive_overlap_list": sorted(step_sensitive),
            "donor_modified_overlap_list": sorted(step_donor_overlap),
        })

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
        "candidate0060_core_surface_files": len(c0060_surface),
        "candidate0060_surface_changed_by_stable_289_to_302": len(c0060_stable_overlap),
        "candidate0060_surface_already_vendor_diverged_on_lisa289": len(c0060_lisa_vendor_overlap),
        "candidate0060_surface_modified_by_miyume_vs_official302": len(c0060_donor_delta),
        "candidate0060_surface_changed_by_both_stable_and_miyume": len(c0060_three_way_overlap),
        "candidate0060_stable_overlap_files": sorted(c0060_stable_overlap),
        "candidate0060_lisa_vendor_overlap_files": sorted(c0060_lisa_vendor_overlap),
        "candidate0060_miyume_delta_files": sorted(c0060_donor_delta),
        "candidate0060_three_way_overlap_files": sorted(c0060_three_way_overlap),
        "batch_a_steps": batch_a_steps,
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
        f"- Candidate0060 planned core files: {len(c0060_surface)}",
        f"- Candidate0060 files changed by official 5.4.289->5.4.302: {len(c0060_stable_overlap)}",
        f"- Candidate0060 files already vendor-diverged in Lisa 5.4.289: {len(c0060_lisa_vendor_overlap)}",
        f"- Candidate0060 files modified by MiYume relative to official 5.4.302: {len(c0060_donor_delta)}",
        f"- Candidate0060 files changed by BOTH stable uplift and MiYume: {len(c0060_three_way_overlap)}",
        "",
        "## Candidate0060 files affected by stable uplift",
        "",
    ]
    lines += [f"- {p}" for p in sorted(c0060_stable_overlap)] or ["- none"]
    lines += ["", "## Batch A incremental provenance", ""]
    for step in batch_a_steps:
        lines += [
            f"### {step['from']} -> {step['to']}",
            "",
            f"- Official changed files: {step['changed_files']}",
            f"- Lisa vendor-overlap files: {step['lisa_vendor_overlap_files']}",
            f"- Sensitive overlap files: {step['sensitive_overlap_files']}",
            f"- Overlap also modified by MiYume: {step['donor_modified_overlap_files']}",
            "",
            "Sensitive overlap paths:",
        ]
        lines += [f"- {p}" for p in step["sensitive_overlap_list"]] or ["- none"]
    lines += ["", "## Candidate0060 MiYume delta on a 5.4.302 base", ""]
    lines += [f"- {p}" for p in sorted(c0060_donor_delta)] or ["- none"]
    lines += ["", "## Sensitive conflict-risk files",
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
    print(f"candidate0060_surface_changed_by_stable={len(c0060_stable_overlap)}")
    print(f"candidate0060_surface_modified_by_miyume={len(c0060_donor_delta)}")
    print(f"candidate0060_surface_three_way_overlap={len(c0060_three_way_overlap)}")
    for step in batch_a_steps:
        print(
            f"batch_a_{step['from']}_to_{step['to']}:changed={step['changed_files']},"
            f"overlap={step['lisa_vendor_overlap_files']},sensitive={step['sensitive_overlap_files']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
