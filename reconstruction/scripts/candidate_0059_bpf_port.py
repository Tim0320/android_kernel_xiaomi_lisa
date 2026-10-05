"""Candidate0059 wrapper for the reviewed Candidate0058 BPF Stage-A payload.

The BPF source bytes remain exactly the Candidate0058 reviewed payload.  This
wrapper only records Candidate0059-named evidence so the new performance build
does not relabel or silently replace the inherited BPF stage.
"""
from pathlib import Path
import json
import shutil

import candidate_0058_bpf_port as inherited

ROOT = inherited.ROOT
META = inherited.META
PATCH = inherited.PATCH
payload = inherited.payload
check_source = inherited.check_source


def _copy_evidence(root: Path) -> None:
    for old, new in (
        ("candidate-0058-bpf-applied.patch", "candidate-0059-bpf-applied.patch"),
        ("candidate-0058-bpf-source.json", "candidate-0059-bpf-source.json"),
        ("candidate-0058-bpf-scope.txt", "candidate-0059-bpf-scope.txt"),
    ):
        src = root / old
        if src.is_file():
            shutil.copyfile(src, root / new)


def apply(root: Path, kernel: Path) -> None:
    inherited.apply(root, kernel)
    _copy_evidence(root)


def install(base, root: Path, kernel: Path) -> None:
    original_sh = base.sh
    applied = False

    def sh(cmd, cwd=None, env=None):
        nonlocal applied
        if cmd and cmd[0] == "make" and not applied:
            apply(root, kernel)
            applied = True
        return original_sh(cmd, cwd=cwd, env=env)

    base.sh = sh


def verify(root: Path) -> None:
    meta = check_source(root / "kernel", root)
    cfg = (root / "candidate-0059.ikconfig").read_text()
    for key in (
        "CONFIG_BPF_SYSCALL",
        "CONFIG_BPF_JIT",
        "CONFIG_CGROUP_BPF",
        "CONFIG_BPF_EVENTS",
        "CONFIG_IRQ_WORK",
        "CONFIG_CFI_CLANG",
        "CONFIG_MODVERSIONS",
    ):
        if key + "=y\n" not in cfg:
            raise RuntimeError("BPF dependency/protection missing: " + key)

    symbols = {}
    for line in (root / "kernel/out/System.map").read_text().splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = fields[1]

    for name in (
        "ringbuf_map_ops",
        "bpf_ringbuf_output_proto",
        "bpf_ringbuf_reserve_proto",
        "bpf_ringbuf_submit_proto",
        "bpf_ringbuf_discard_proto",
        "bpf_ringbuf_query_proto",
    ):
        if name not in symbols:
            raise RuntimeError("BPF linked object missing: " + name)

    for name in (
        "bpf_ringbuf_output",
        "bpf_ringbuf_reserve",
        "bpf_ringbuf_submit",
        "bpf_ringbuf_discard",
        "bpf_ringbuf_query",
    ):
        if not any(
            (n == name or n.startswith(name + ".")) and t in ("T", "t")
            for n, t in symbols.items()
        ):
            raise RuntimeError("BPF helper has no linked code: " + name)

    for name in ("ringbuf.o", "verifier.o"):
        p = root / "kernel/out/kernel/bpf" / name
        if not p.is_file() or not p.stat().st_size:
            raise RuntimeError("BPF compiler object absent: " + name)

    result = dict(
        candidate="0059",
        inherited_stage="candidate0058-ringbuf-v1",
        source_gate="PASS",
        linked_gate="PASS",
        source_files=len(meta["files"]),
        full_bpf510_parity=False,
        target_device_tested=False,
        qemu_test="separate verifier workflow step",
    )
    (root / "candidate-0059-bpf-verification.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print("LISA_CANDIDATE_0059_BPF_LINKED_GATE=PASS", flush=True)
