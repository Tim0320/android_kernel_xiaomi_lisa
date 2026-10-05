#!/usr/bin/env python3
from pathlib import Path
import argparse, json, subprocess, tempfile

UPSTREAM_BASE = "upstream-v5.4.292"
UPSTREAM_TARGET = "upstream-v5.4.296"
AOSP_BASE = "aosp-android11-5.4.292"
AOSP_TARGET = "aosp-android11-5.4.296"
CLO_TARGET = "clo-msm-5.4-r1-rel"

def git(root, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )

def blob(root, ref, path):
    p = git(root, "show", f"{ref}:{path}", check=False)
    return None if p.returncode else p.stdout

def work(root, path):
    p = root / path
    return p.read_bytes() if p.is_file() else None

def ref_exists(root, ref):
    return git(root, "rev-parse", "--verify", "--quiet", ref, check=False).returncode == 0

def mergeable(ours, base, theirs):
    if None in (ours, base, theirs):
        return False
    if any(b"\0" in x[:8192] for x in (ours, base, theirs)):
        return False
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for name, data in (("ours", ours), ("base", base), ("theirs", theirs)):
            (d / name).write_bytes(data)
        p = subprocess.run(
            ["git", "merge-file", "-p", str(d/"ours"), str(d/"base"), str(d/"theirs")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return p.returncode == 0

def classify_aosp(ub, ut, ab, at):
    if ab is None and at is None:
        return "AOSP_PATH_ABSENT"
    if ab == ub and at == ut:
        return "AOSP_FOLLOWS_UPSTREAM_STABLE"
    if at == ut:
        return "AOSP_TARGET_EQUALS_UPSTREAM_TARGET"
    if ab == ub and ab != at:
        return "AOSP_ADAPTS_STABLE_TARGET"
    if ab == at:
        return "AOSP_UNCHANGED_ACROSS_BATCH"
    return "AOSP_ANDROID_DIVERGED"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("candidate-0061-batch-b-oracle.json"))
    args = ap.parse_args()
    root = args.source.resolve()

    if not ref_exists(root, AOSP_BASE) or not ref_exists(root, AOSP_TARGET):
        raise RuntimeError("AOSP android11-5.4 oracle refs are missing")

    clo_available = ref_exists(root, CLO_TARGET)
    paths = git(root, "diff", "--name-only", "--no-renames", UPSTREAM_BASE, UPSTREAM_TARGET).stdout.decode().splitlines()

    rows = []
    semantic = []
    counts = {}
    for path in paths:
        ub = blob(root, UPSTREAM_BASE, path)
        ut = blob(root, UPSTREAM_TARGET, path)
        ours = work(root, path)

        if ours == ut:
            cls = "ALREADY_PRESENT"
        elif ours == ub:
            cls = "DIRECT"
        elif mergeable(ours, ub, ut):
            cls = "AUTO_3WAY"
        else:
            cls = "SEMANTIC_REVIEW"

        ab = blob(root, AOSP_BASE, path)
        at = blob(root, AOSP_TARGET, path)
        clo = blob(root, CLO_TARGET, path) if clo_available else None

        row = {
            "path": path,
            "class": cls,
            "vendor_diverged_from_upstream_base": ours != ub,
            "aosp_oracle": classify_aosp(ub, ut, ab, at),
            "aosp_base_exists": ab is not None,
            "aosp_target_exists": at is not None,
            "aosp_base_equals_upstream_base": ab == ub,
            "aosp_target_equals_upstream_target": at == ut,
            "aosp_changed_across_batch": ab != at,
            "clo_oracle_available": clo_available,
            "clo_path_exists": clo is not None,
            "clo_equals_upstream_target": clo == ut if clo_available else None,
            "clo_equals_lisa_worktree": clo == ours if clo_available else None,
        }
        rows.append(row)
        counts[cls] = counts.get(cls, 0) + 1
        if cls == "SEMANTIC_REVIEW":
            semantic.append(row)

    result = {
        "candidate": "0061",
        "batch": "B",
        "from": "5.4.292",
        "to": "5.4.296",
        "provenance_source": "official linux-stable",
        "android_semantic_oracle": "android11-5.4.292_r00 -> android11-5.4.296_r00",
        "qualcomm_semantic_oracle": "CLO kernel.lnx.5.4.r1-rel (best-effort snapshot)",
        "clo_oracle_available": clo_available,
        "counts": counts,
        "semantic_review_count": len(semantic),
        "semantic_review": semantic,
        "files": rows,
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")

    print("C0061_BATCH_B_ORACLE_SCAN=PASS")
    print("semantic_review_count=" + str(len(semantic)))
    for row in semantic:
        print(
            "SEMANTIC_REVIEW",
            row["path"],
            "aosp=" + row["aosp_oracle"],
            "clo_exists=" + str(row["clo_path_exists"]),
            "clo_eq_lisa=" + str(row["clo_equals_lisa_worktree"]),
        )

if __name__ == "__main__":
    main()
