#!/usr/bin/env python3
"""Generate Candidate0059 wrappers from the reviewed Candidate0058 recipe set.

Candidate0058 remains the inherited build architecture: module ownership,
battery/UFS fixes, fixed-region boot packaging and BPF Stage-A. Candidate0059
changes only the release identity plus the reviewed performance-stage hook.
"""
from pathlib import Path
import ast
import hashlib
import json
import py_compile
import re

import candidate_0058_factory as base58

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "reconstruction/scripts"

PERF_CHECKPOINT = (
    "candidate-0059-performance-source.json",
    "candidate-0059-performance-scope.txt",
    "kernel/include/linux/android_kabi.h",
    "kernel/include/linux/pkg_stat.h",
    "kernel/include/linux/sched.h",
    "kernel/include/linux/sched/user.h",
    "kernel/drivers/mihw/Kconfig",
    "kernel/drivers/mihw/Makefile",
    "kernel/drivers/mihw/migt.c",
    "kernel/kernel/sched/Makefile",
    "kernel/kernel/sched/pkg_state.c",
    "kernel/kernel/sched/pkg_bridge.c",
    "kernel/kernel/sched/pkg_core.c",
    "kernel/kernel/sched/migt_sched.c",
    "kernel/kernel/sched/migt_render.c",
    "kernel/kernel/sched/glk.c",
    "kernel/kernel/fork.c",
    "kernel/kernel/user.c",
    "kernel/kernel/exit.c",
    "kernel/kernel/cred.c",
    "kernel/kernel/sched/walt/walt.c",
    "kernel/kernel/time/timekeeping.c",
    "kernel/out/drivers/mihw/migt.o",
    "kernel/out/kernel/sched/pkg_state.o",
    "kernel/out/kernel/sched/pkg_bridge.o",
    "kernel/out/kernel/sched/pkg_core.o",
    "kernel/out/kernel/sched/migt_sched.o",
    "kernel/out/kernel/sched/migt_render.o",
    "kernel/out/kernel/sched/glk.o",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Candidate0059 factory anchor count={count}: {old[:120]!r}")
    return text.replace(old, new, 1)


def generate_base() -> dict[str, str]:
    base58.main()
    out: dict[str, str] = {}
    for old_name, expected in base58.EXPECTED.items():
        path = SCRIPT_DIR / old_name
        data = path.read_bytes()
        if sha256(data) != expected:
            raise RuntimeError("Candidate0058 generated input changed: " + old_name)
        new_name = old_name.replace("0058", "0059")
        out[new_name] = data.decode().replace("0058", "0059")
    return out


def patch_identity(files: dict[str, str]) -> None:
    name = "candidate_0059_identity.py"
    text = files[name]
    text = text.replace("KBUILD_BUILD_VERSION='58'", "KBUILD_BUILD_VERSION='59'")
    text = text.replace("'build_version': 58", "'build_version': 59")
    text = text.replace("'build_version': 58,", "'build_version': 59,")
    text = text.replace("if '#58 SMP PREEMPT ' not in text", "if '#59 SMP PREEMPT ' not in text")
    files[name] = text

    test = "test_candidate_0059_identity.py"
    t = files[test]
    t = t.replace("'#58 SMP PREEMPT ", "'#59 SMP PREEMPT ")
    t = t.replace("replace('#58','#56')", "replace('#59','#58')")
    files[test] = t


def patch_build(files: dict[str, str]) -> None:
    owner_name = "candidate_0059_ownership_patch.py"
    owner_blob = blob_sha(files[owner_name].encode())

    name = "candidate_0059_build.py"
    text = files[name]
    text = re.sub(
        r"('candidate_0059_ownership_patch\.py':\s*)'[0-9a-f]{40}'",
        lambda m: m.group(1) + repr(owner_blob),
        text,
        count=1,
    )

    text = once(
        text,
        "        'install_bpf58(base, ROOT, KERNEL)\\n\\n' + hook)",
        "        'install_bpf58(base, ROOT, KERNEL)\\n'\n"
        "        'from candidate_0059_perf_port import install as install_perf59\\n'\n"
        "        'install_perf59(base, ROOT, KERNEL)\\n\\n' + hook)",
    )

    text = once(
        text,
        "'test_candidate_0059_bpf_port.py'):",
        "'test_candidate_0059_bpf_port.py', 'candidate_0059_perf_port.py'):",
    )

    text = once(
        text,
        "from candidate_0059_bpf_port import check_source\n"
        "    check_source(ROOT / 'kernel')\n",
        "from candidate_0059_bpf_port import check_source\n"
        "    check_source(ROOT / 'kernel')\n"
        "    from candidate_0059_perf_port import check_source as check_perf_source\n"
        "    check_perf_source(ROOT)\n",
    )

    text = text.replace(
        "candidate=Lisa Candidate0059 privileged BPF5.10 ring-buffer stage1 on verified0057\\n",
        "candidate=Lisa Candidate0059 Android16 performance restoration on verified0058\\n",
    )
    text = text.replace(
        "baseline=Candidate0057 runtime ownership plus0056battery and0055UFS\\n",
        "baseline=Candidate0058 BPF Stage-A plus Candidate0057 Wi-Fi ownership, Candidate0056 battery and Candidate0055 UFS\\n",
    )
    text = text.replace(
        "mutation=first-stage BPF5.10 ringbuf helpers+verifier+mmap/poll; preserve vendor module ownership\\n",
        "mutation=retain BPF5.10 Stage-A and restore package-runtime/MIGT/FREQ_QOS performance chain\\n",
    )
    text = text.replace(
        "unchanged=battery algorithms/UFS/procfs/CFI/PAS/display/GPU/audio/thermal/boot layout; no system/vendor APK or modem firmware changes\\n",
        "unchanged=battery algorithms/UFS/procfs/CFI/PAS/display/GPU/audio/thermal/boot layout; no SELinux weakening, thermal bypass or Metis alias\\n",
    )
    text = text.replace(
        "not_claimed=full BPF5.10 parity, Android16 ROM repair, cellular/graphics fix, target verifier runtime pass\\n",
        "not_claimed=full BPF5.10 parity, Android14 debug-root-cause repair, device performance pass or Android16 jank fix before phone evidence\\n",
    )

    text = once(
        text,
        "from candidate_0059_bpf_port import verify as verify_bpf\n"
        "    verify_bpf(ROOT)\n",
        "from candidate_0059_bpf_port import verify as verify_bpf\n"
        "    verify_bpf(ROOT)\n"
        "    from candidate_0059_perf_port import verify as verify_perf\n"
        "    verify_perf(ROOT)\n",
    )
    files[name] = text


def patch_artifacts(files: dict[str, str]) -> None:
    name = "candidate_0059_artifacts.py"
    text = files[name]
    addition = "REQUIRED += " + repr(PERF_CHECKPOINT) + "\n\n"
    text = once(text, "OPTIONAL = (", addition + "OPTIONAL = (")
    files[name] = text


def main() -> None:
    files = generate_base()
    patch_identity(files)
    patch_build(files)
    patch_artifacts(files)

    generated = {}
    for name, text in files.items():
        compile(text, name, "exec")
        path = SCRIPT_DIR / name
        path.write_text(text)
        generated[name] = sha256(text.encode())

    for required in (
        "candidate_0059_bpf_port.py",
        "candidate_0059_perf_port.py",
        "test_candidate_0059_bpf_port.py",
    ):
        py_compile.compile(str(SCRIPT_DIR / required), doraise=True)

    (ROOT / "candidate-0059-generated-recipes.json").write_text(
        json.dumps(generated, indent=2, sort_keys=True) + "\n"
    )
    print("LISA_CANDIDATE_0059_RECIPE_GENERATION=PASS", flush=True)


if __name__ == "__main__":
    main()
