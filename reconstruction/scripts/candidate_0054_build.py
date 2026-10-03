#!/usr/bin/env python3
"""Build Candidate0054 from the pinned, previously built Candidate0053 recipe.

All inherited shell gates remain in the pinned parent workflow. Only the
failed symbolic fault-capture gate is replaced by a raw/latch gate.
"""
import argparse
import ast
import hashlib
import os
from pathlib import Path
import py_compile
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "reconstruction/scripts/candidate_0053_build.py"
PARENT_SHA = "d3111485e075156687c5eee50546ba42417dd2fa"
WORKFLOW = ROOT / ".github/workflows/build-lisa-candidate-0053-arm64-fault-capture.yml"
WORKFLOW_SHA = "2b083a6714978f7090b82a9228d0ec272e2dbcde"
REPLACEMENT = '''def patch_arm64_fault_frontload():
    from candidate_0054_fault_patch import apply
    apply(ROOT, KERNEL)
'''


def checked(path: Path, sha: str) -> str:
    data = path.read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if actual != sha:
        raise RuntimeError(f"Pinned parent changed: {path.name}: {actual} != {sha}")
    return data.decode("utf-8")


def relabel(value: str) -> str:
    for old, new in (("Candidate0053", "Candidate0054"), ("Candidate 0053", "Candidate 0054"),
                     ("candidate_0053", "candidate_0054"), ("candidate-0053", "candidate-0054"),
                     ("CANDIDATE_0053", "CANDIDATE_0054"), ("LISA0053", "LISA0054"),
                     ("candidate0053", "candidate0054")):
        value = value.replace(old, new)
    return value


def transformed_source() -> str:
    text = relabel(checked(PARENT, PARENT_SHA))
    tree = ast.parse(text, filename=str(PARENT))
    found = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name == "patch_arm64_fault_frontload"]
    if len(found) != 1:
        raise RuntimeError("Expected exactly one inherited fault-capture function")
    node = found[0]
    lines = text.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [REPLACEMENT + "\n"]
    text = "".join(lines)
    compile(text, "candidate0054_resolved", "exec")
    if "pc=%pS lr=%pS" in text:
        raise RuntimeError("Obsolete first symbolic fault formatter survived transformation")
    return text


def preflight() -> str:
    checked(WORKFLOW, WORKFLOW_SHA)
    text = transformed_source()
    for name in ("candidate_0046_build.py", "candidate_0053_build.py",
                 "candidate_0054_fault_patch.py", "candidate_0054_build.py"):
        py_compile.compile(str(ROOT / "reconstruction/scripts" / name), doraise=True)
    print("LISA_CANDIDATE_0054_PYTHON_PREFLIGHT=PASS", flush=True)
    return text


def resolve_env(value: str) -> str:
    value = str(value)
    value = value.replace("${{ github.token }}", os.environ.get("GH_TOKEN", ""))
    value = value.replace("${{ runner.temp }}", os.environ.get("RUNNER_TEMP", ""))
    if "${{" in value:
        raise RuntimeError("Unsupported expression in pinned parent step environment")
    return value


def run_parent_phase(phase: str) -> None:
    import yaml
    document = yaml.safe_load(checked(WORKFLOW, WORKFLOW_SHA))
    steps = document["jobs"]["build"]["steps"]
    names = [step.get("name", "") for step in steps]
    if phase == "prepare":
        wanted = ["Install stock-era clang 11.0.2", "Download exact stock IKHEADERS",
                  "Fetch preserved Candidate 0018 IKCONFIG from Candidate 0040"]
        selected = [steps[names.index(name)] for name in wanted]
    else:
        first = names.index("Download exact stock msm_drm import oracle")
        last = names.index("Final Candidate 0053 static gate")
        selected = steps[first:last + 1]
    work = ROOT / "candidate-0054-checks"
    work.mkdir(exist_ok=True)
    for index, step in enumerate(selected, 1):
        name = relabel(step["name"])
        print(f"::group::{name}", flush=True)
        if step["name"] == "Verify Candidate 0053 ARM64 fault front-load diagnostics":
            from candidate_0054_fault_patch import verify
            verify(ROOT)
        else:
            if "run" not in step or "uses" in step:
                raise RuntimeError(f"Unexpected non-shell verification step: {name}")
            env = os.environ.copy()
            env.update({key: resolve_env(value) for key, value in step.get("env", {}).items()})
            shell = work / f"{phase}-{index:02d}.sh"
            shell.write_text(relabel(step["run"]))
            subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", str(shell)],
                           cwd=ROOT, env=env, check=True)
        print("::endgroup::", flush=True)
    if phase == "verify":
        checksum = (ROOT / "boot.img.sha256").read_text().split()[0]
        if digest(ROOT / "boot.img") != checksum:
            raise RuntimeError("Final boot.img SHA256 validation failed")
        print("LISA_CANDIDATE_0054_ARTIFACT_CHECKSUM_GATE=PASS", flush=True)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for part in iter(lambda: file.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def build() -> None:
    source = preflight()
    (ROOT / "candidate-0054-resolved-builder.py").write_text(source)
    # Preserve the source recipe's ROOT calculation, but execute only the
    # parsed/replaced recipe. The parent recipe itself is never edited.
    scope = {"__file__": str(PARENT), "__name__": "__main__"}
    exec(compile(source, "candidate0054_resolved", "exec"), scope)
    manifest = (
        "candidate=Lisa Candidate0054 raw first-fault latch and bounded persistence\n"
        "baseline=Candidate0053 da8271c; no PAS/audio/watchdog/CFI behavior change\n"
        f"package_commit={os.environ.get('GITHUB_SHA', 'local')}\n"
        f"workflow_run={os.environ.get('GITHUB_RUN_ID', 'local')}\n"
        f"candidate_0054_image_sha256={digest(ROOT / 'candidate-0054-Image')}\n"
        f"candidate_0054_boot_sha256={digest(ROOT / 'boot.img')}\n"
        "mutation=publish numeric registers before printk; deferred raw line; append immutable latch to existing bounded mtdoops snapshots; module relocation map\n"
        "diagnostic_only=1\n"
        "runtime_root_cause=unconfirmed; missing symbolic output does not identify original crash function\n"
        "LISA_CANDIDATE_0054_FINAL_GATE=PASS\n"
    )
    (ROOT / "candidate-0054-manifest.txt").write_text(manifest)
    print(manifest, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("preflight", "prepare", "build", "verify"), nargs="?", default="build")
    args = parser.parse_args()
    if args.phase == "preflight":
        preflight()
    elif args.phase in ("prepare", "verify"):
        preflight()
        run_parent_phase(args.phase)
    else:
        build()


if __name__ == "__main__":
    main()
