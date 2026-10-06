#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import subprocess
import tempfile

from candidate_0061_direct_302_manual import adapt
from candidate_0061_direct_302_reviewed import REVIEWED_SEMANTICS

UPSTREAM_BASE = "upstream-v5.4.289"
UPSTREAM_TARGET = "upstream-v5.4.302"


def git(root, *args, check=True, input_bytes=None):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        input=input_bytes,
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


def write(root, path, data):
    p = root / path
    if data is None:
        if p.exists():
            p.unlink()
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def merge3(ours, base, target):
    if None in (ours, base, target):
        raise RuntimeError("three-way add/delete conflict")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for name, data in (("ours", ours), ("base", base), ("target", target)):
            (d / name).write_bytes(data)
        p = subprocess.run(
            ["git", "merge-file", "-p", str(d / "ours"), str(d / "base"), str(d / "target")],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if p.returncode:
            raise RuntimeError("three-way merge conflict")
        return p.stdout


def apply_upstream_hunks_with_reject(root, path):
    patch = git(
        root, "diff", "--binary", "--no-renames",
        UPSTREAM_BASE, UPSTREAM_TARGET, "--", path
    ).stdout
    if not patch:
        return True, "", ""
    p = git(
        root, "apply", "--reject", "--whitespace=nowarn", "-",
        check=False, input_bytes=patch
    )
    rej = root / (path + ".rej")
    rej_text = rej.read_text(errors="replace") if rej.exists() else ""
    return p.returncode == 0 and not rej.exists(), p.stderr.decode(errors="replace"), rej_text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--scan", type=Path, required=True)
    ap.add_argument("--report", type=Path, default=Path("candidate-0061-direct-302-apply.json"))
    args = ap.parse_args()

    root = args.source.resolve()
    scan = json.loads(args.scan.read_text())
    rows = scan.get("files", [])
    if len(rows) != 1760:
        raise RuntimeError(f"Direct-302 apply expected 1760 scan rows, got {len(rows)}")
    if scan.get("reviewed_semantic_count") != 34 or scan.get("unresolved_semantic_count") != 0:
        raise RuntimeError("Direct-302 apply requires reviewed=34 unresolved=0")

    stats = {
        "ALREADY_PRESENT": 0,
        "DIRECT": 0,
        "AUTO_3WAY": 0,
        "ADAPT": 0,
        "NOT_APPLICABLE": 0,
    }
    out = []

    for row in rows:
        path = row["path"]
        cls = row["class"]
        base = blob(root, UPSTREAM_BASE, path)
        target = blob(root, UPSTREAM_TARGET, path)
        ours = work(root, path)

        if cls == "ALREADY_PRESENT":
            if ours != target:
                raise RuntimeError(f"{path}: scan said ALREADY_PRESENT but worktree drifted")
            applied = "ALREADY_PRESENT"

        elif cls == "DIRECT":
            if ours != base:
                raise RuntimeError(f"{path}: scan said DIRECT but worktree no longer matches 5.4.289")
            write(root, path, target)
            applied = "DIRECT"

        elif cls == "AUTO_3WAY":
            merged = merge3(ours, base, target)
            write(root, path, merged)
            applied = "AUTO_3WAY"

        elif cls == "SEMANTIC_REVIEW":
            decision = REVIEWED_SEMANTICS.get(path)
            if not decision:
                raise RuntimeError(f"{path}: missing reviewed semantic decision")
            segments = row.get("provenance_segments", [])
            reviewed_segments = decision.get("reviewed_segments", [])
            if not set(segments).issubset(set(reviewed_segments)):
                raise RuntimeError(
                    f"{path}: registry does not cover segments {segments}; "
                    f"reviewed={reviewed_segments}"
                )

            resolution = decision["resolution"]
            if resolution == "NOT_APPLICABLE":
                applied = "NOT_APPLICABLE"
            elif resolution == "ADAPT":
                clean, stderr, reject = apply_upstream_hunks_with_reject(root, path)
                adapter = None
                always_adapt = bool(decision.get("always_adapt"))
                if not clean or always_adapt:
                    try:
                        adapter = adapt(
                            root, path, UPSTREAM_TARGET,
                            lambda p: blob(root, UPSTREAM_TARGET, p),
                            reviewed_segments,
                        )
                    except Exception as exc:
                        raise RuntimeError(
                            f"{path}: Direct-302 semantic adapter failed: {exc}\n"
                            f"git-apply-stderr:\n{stderr}\n"
                            f"reject:\n{reject}"
                        ) from exc

                    rej = root / (path + ".rej")
                    if rej.exists():
                        rej.unlink()
                applied = "ADAPT"
            else:
                raise RuntimeError(f"{path}: unsupported semantic resolution {resolution}")
        else:
            raise RuntimeError(f"{path}: unsupported scan class {cls}")

        stats[applied] += 1
        out.append({
            "path": path,
            "scan_class": cls,
            "applied_class": applied,
            "provenance_segments": row.get("provenance_segments", []),
        })

    if sum(stats.values()) != 1760:
        raise RuntimeError(f"Direct-302 apply accounting mismatch: {stats}")

    rejects = list(root.rglob("*.rej"))
    if rejects:
        raise RuntimeError("Direct-302 apply left reject files: " + ", ".join(str(x) for x in rejects))

    p = git(root, "diff", "--check", check=False)
    if p.returncode:
        raise RuntimeError(
            "git diff --check failed\n" +
            p.stdout.decode(errors="replace") +
            p.stderr.decode(errors="replace")
        )

    makefile = (root / "Makefile").read_text()
    if "SUBLEVEL = 302\n" not in makefile:
        raise RuntimeError("Direct-302 source identity is not SUBLEVEL=302")

    result = {
        "candidate": "0061",
        "mode": "DIRECT_5_4_289_TO_5_4_302",
        "from": "5.4.289",
        "to": "5.4.302",
        "counts": stats,
        "files": out,
        "candidate0059_reference_untouched": True,
        "source_identity": "5.4.302",
        "git_diff_check": "PASS",
    }
    args.report.write_text(json.dumps(result, indent=2) + "\n")

    print("C0061_DIRECT_302_APPLY=PASS")
    print("changed_file_count=1760")
    print("source_identity=5.4.302")
    print("git_diff_check=PASS")
    print(json.dumps(stats, sort_keys=True))


if __name__ == "__main__":
    main()
