#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import subprocess
import tempfile

UPSTREAM_BASE = "upstream-v5.4.289"
UPSTREAM_TARGET = "upstream-v5.4.302"
SEGMENTS = [
    ("A", "upstream-v5.4.289", "upstream-v5.4.292"),
    ("B", "upstream-v5.4.292", "upstream-v5.4.296"),
    ("C", "upstream-v5.4.296", "upstream-v5.4.299"),
    ("D", "upstream-v5.4.299", "upstream-v5.4.302"),
]
MIYUME_TARGET = "miyume-sm8350-5.4.302"
AOSP_TARGET = "aosp-android11-5.4.302"
CLO_TARGET = "clo-msm-5.4-r1-rel"

# Paths that are textually mergeable but semantically incompatible with the
# frozen Lisa/C0059 downstream contract. They must enter reviewed resolution.
FORCED_SEMANTIC_REVIEW = {
    "drivers/base/power/runtime.c",
}

SOC_MARKERS = (
    "SM8350", "sm8350", "LAHAINA", "lahaina", "venus",
    "MACH_XIAOMI_SM8350", "ARCH_LAHAINA",
)

def git(root, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )

def ref_exists(root, ref):
    return git(root, "rev-parse", "--verify", "--quiet", ref, check=False).returncode == 0

def blob(root, ref, path):
    p = git(root, "show", f"{ref}:{path}", check=False)
    return None if p.returncode else p.stdout

def work(root, path):
    p = root / path
    return p.read_bytes() if p.is_file() else None

def mergeable(ours, base, target):
    if None in (ours, base, target):
        return False
    if any(b"\0" in x[:8192] for x in (ours, base, target)):
        return False
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for name, data in (("ours", ours), ("base", base), ("target", target)):
            (d / name).write_bytes(data)
        p = subprocess.run(
            ["git", "merge-file", "-p", str(d/"ours"), str(d/"base"), str(d/"target")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return p.returncode == 0

def segment_membership(root, path):
    labels = []
    for label, a, b in SEGMENTS:
        if blob(root, a, path) != blob(root, b, path):
            labels.append(label)
    return labels

def marker_hits(data):
    if data is None or b"\0" in data[:8192]:
        return []
    text = data.decode("utf-8", errors="ignore")
    return [m for m in SOC_MARKERS if m in text]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("candidate-0061-direct-302-scan.json"))
    args = ap.parse_args()
    root = args.source.resolve()

    required = [UPSTREAM_BASE, UPSTREAM_TARGET, MIYUME_TARGET, AOSP_TARGET]
    required += [x for _, a, b in SEGMENTS for x in (a, b)]
    for ref in sorted(set(required)):
        if not ref_exists(root, ref):
            raise RuntimeError(f"required ref missing: {ref}")

    clo_available = ref_exists(root, CLO_TARGET)
    paths = git(
        root, "diff", "--name-only", "--no-renames", UPSTREAM_BASE, UPSTREAM_TARGET
    ).stdout.decode().splitlines()

    counts = {}
    rows = []
    semantic = []

    for path in paths:
        base = blob(root, UPSTREAM_BASE, path)
        target = blob(root, UPSTREAM_TARGET, path)
        ours = work(root, path)

        if path in FORCED_SEMANTIC_REVIEW and ours != target:
            cls = "SEMANTIC_REVIEW"
        elif ours == target:
            cls = "ALREADY_PRESENT"
        elif ours == base:
            cls = "DIRECT"
        elif mergeable(ours, base, target):
            cls = "AUTO_3WAY"
        else:
            cls = "SEMANTIC_REVIEW"

        miyume = blob(root, MIYUME_TARGET, path)
        aosp = blob(root, AOSP_TARGET, path)
        clo = blob(root, CLO_TARGET, path) if clo_available else None

        row = {
            "path": path,
            "class": cls,
            "provenance_segments": segment_membership(root, path),
            "vendor_diverged_from_5_4_289": ours != base,
            "miyume_path_exists": miyume is not None,
            "miyume_equals_upstream_302": miyume == target,
            "miyume_equals_lisa_worktree": miyume == ours,
            "miyume_soc_specific_marker_hits": marker_hits(miyume),
            "aosp_302_path_exists": aosp is not None,
            "aosp_302_equals_upstream_302": aosp == target,
            "aosp_302_equals_lisa_worktree": aosp == ours,
            "clo_available": clo_available,
            "clo_path_exists": clo is not None,
            "clo_equals_upstream_302": (clo == target) if clo_available else None,
            "clo_equals_lisa_worktree": (clo == ours) if clo_available else None,
        }
        rows.append(row)
        counts[cls] = counts.get(cls, 0) + 1
        if cls == "SEMANTIC_REVIEW":
            semantic.append(row)

    result = {
        "candidate": "0061",
        "mode": "DIRECT_5_4_289_TO_5_4_302",
        "from": "5.4.289",
        "to": "5.4.302",
        "canonical_provenance": "official linux-stable",
        "provenance_segments": {
            "A": "5.4.289->5.4.292",
            "B": "5.4.292->5.4.296",
            "C": "5.4.296->5.4.299",
            "D": "5.4.299->5.4.302",
        },
        "preferred_downstream_oracle": "MiYume SM8350/Xiaomi 5.4.302",
        "android_gki_endpoint_oracle": "AOSP android11-5.4.302_r00",
        "qualcomm_fallback_oracle": "CLO kernel.lnx.5.4.r1-rel",
        "clo_available": clo_available,
        "counts": counts,
        "semantic_review_count": len(semantic),
        "semantic_review": semantic,
        "files": rows,
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")

    print("C0061_DIRECT_302_SCAN=PASS")
    print("changed_file_count=" + str(len(rows)))
    print("semantic_review_count=" + str(len(semantic)))
    for row in semantic:
        print(
            "DIRECT302_SEMANTIC_REVIEW",
            row["path"],
            "segments=" + ",".join(row["provenance_segments"]),
            "miyume_eq_302=" + str(row["miyume_equals_upstream_302"]),
            "aosp_eq_302=" + str(row["aosp_302_equals_upstream_302"]),
            "soc_markers=" + ",".join(row["miyume_soc_specific_marker_hits"]),
        )

if __name__ == "__main__":
    main()
