"""Candidate0059 performance-source installer and verifier.

Stages1-7 plus Stage9 are applied exactly once immediately before the first
kernel make.  The same hook also enables the three stock-proven performance
config symbols before olddefconfig/compile.  OEM_KERNEL is retained as a stock
oracle only and is not fabricated as a runtime requirement.
"""
from pathlib import Path
import hashlib
import json
import subprocess

import candidate_0059_state_layer as stage1
import candidate_0059_stage2_hooks as stage2
import candidate_0059_stage3_accounting as stage3
import candidate_0059_stage4_migt_sched as stage4
import candidate_0059_stage5_game_load as stage5
import candidate_0059_stage6_render as stage6
import candidate_0059_stage7_migt_control as stage7
import candidate_0059_stage9_freq_qos as stage9

PERF_SOURCE_FILES = (
    "include/linux/android_kabi.h",
    "include/linux/pkg_stat.h",
    "include/linux/sched.h",
    "include/linux/sched/user.h",
    "drivers/mihw/Kconfig",
    "drivers/mihw/Makefile",
    "drivers/mihw/migt.c",
    "kernel/sched/Makefile",
    "kernel/sched/pkg_state.c",
    "kernel/sched/pkg_bridge.c",
    "kernel/sched/pkg_core.c",
    "kernel/sched/migt_sched.c",
    "kernel/sched/migt_render.c",
    "kernel/sched/glk.c",
    "kernel/fork.c",
    "kernel/user.c",
    "kernel/exit.c",
    "kernel/cred.c",
    "kernel/sched/walt/walt.c",
    "kernel/time/timekeeping.c",
)

REQUIRED_CONFIG = (
    "CONFIG_MIHW=y",
    "CONFIG_PACKAGE_RUNTIME_INFO=y",
    "CONFIG_MIGT=y",
    "CONFIG_CFI_CLANG=y",
    "CONFIG_MODVERSIONS=y",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def apply_sources(root: Path, kernel: Path) -> None:
    stage1.apply(kernel)
    stage2.apply(kernel)
    stage3.apply(kernel)
    stage4.apply(kernel)
    stage5.apply(kernel)
    stage6.apply(kernel)
    stage7.apply(kernel)
    stage9.apply(kernel)
    report = stage9.verify(kernel)
    if report["result"] != "PASS":
        raise RuntimeError("Candidate0059 Stage9 source verification failed: " + repr(report["failures"]))

    record = {
        "candidate": "0059",
        "stage_chain": ["1", "2", "3", "4", "5", "6", "7", "9"],
        "stage8": "API-audit-only",
        "target_ref": stage9.TARGET_REF,
        "source_gate": "PASS",
        "runtime_tested": False,
        "files": {},
    }
    for rel in PERF_SOURCE_FILES:
        path = kernel / rel
        if not path.is_file():
            raise RuntimeError("Candidate0059 performance source missing after apply: " + rel)
        record["files"][rel] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    (root / "candidate-0059-performance-source.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )
    (root / "candidate-0059-performance-scope.txt").write_text(
        "scope=Candidate0059 Android16 performance restoration\n"
        "stages=1,2,3,4,5,6,7,9; stage8 is API audit only\n"
        "interfaces=package-runtime,MIGT,/dev/migt,FREQ_QOS min/max\n"
        "not_added=/dev/metis alias,unknown ioctl success,global max pin,thermal disable,core_ctl boost\n"
        "iorap_strategy=defer-outside-c0059\n"
        "developer_options_android14_root_cause=unresolved outside candidate kernel\n"
        "android16_controlled_runtime_props=0/0/1/1\n"
        "runtime_validation=pending device test\n"
        "CANDIDATE0059_PERFORMANCE_SOURCE_GATE=PASS\n"
    )


def enable_config(kernel: Path) -> None:
    cfg = kernel / "out/.config"
    script = kernel / "scripts/config"
    if not cfg.is_file():
        raise RuntimeError("Candidate0059 config hook ran before out/.config existed")
    subprocess.run(
        [
            str(script),
            "--file",
            str(cfg),
            "-e",
            "MIHW",
            "-e",
            "PACKAGE_RUNTIME_INFO",
            "-e",
            "MIGT",
        ],
        check=True,
    )


def check_source(root: Path) -> dict:
    kernel = root / "kernel"
    report = stage9.verify(kernel)
    if report["result"] != "PASS":
        raise RuntimeError("Candidate0059 Stage9 source gate failed: " + repr(report["failures"]))
    record = json.loads((root / "candidate-0059-performance-source.json").read_text())
    for rel, expected in record["files"].items():
        path = kernel / rel
        if not path.is_file() or sha256(path) != expected["sha256"]:
            raise RuntimeError("Candidate0059 performance source changed after apply: " + rel)
    return record


def install(base, root: Path, kernel: Path) -> None:
    original_sh = base.sh
    applied = False

    def sh(cmd, cwd=None, env=None):
        nonlocal applied
        if cmd and cmd[0] == "make" and not applied:
            apply_sources(root, kernel)
            enable_config(kernel)
            applied = True
        result = original_sh(cmd, cwd=cwd, env=env)
        if cmd and cmd[0] == "make" and applied:
            cfg = kernel / "out/.config"
            if cfg.is_file():
                text = cfg.read_text()
                for token in REQUIRED_CONFIG[:3]:
                    if token + "\n" not in text:
                        raise RuntimeError("Candidate0059 config lost after make: " + token)
        return result

    base.sh = sh


def verify(root: Path) -> None:
    check_source(root)
    cfg = (root / "candidate-0059.ikconfig").read_text()
    for token in REQUIRED_CONFIG:
        if token + "\n" not in cfg:
            raise RuntimeError("Candidate0059 embedded config missing: " + token)
    if "CONFIG_CFI_PERMISSIVE=y\n" in cfg:
        raise RuntimeError("Candidate0059 unexpectedly enabled permissive CFI")

    system_map = (root / "kernel/out/System.map").read_text()
    for symbol in ("migt_init", "migt_sched_init", "game_load_init", "pkg_init"):
        if not any(line.split()[-1] == symbol for line in system_map.splitlines() if line.split()):
            raise RuntimeError("Candidate0059 linked performance symbol missing: " + symbol)

    objects = (
        "kernel/out/drivers/mihw/migt.o",
        "kernel/out/kernel/sched/pkg_state.o",
        "kernel/out/kernel/sched/pkg_bridge.o",
        "kernel/out/kernel/sched/pkg_core.o",
        "kernel/out/kernel/sched/migt_sched.o",
        "kernel/out/kernel/sched/migt_render.o",
        "kernel/out/kernel/sched/glk.o",
    )
    for rel in objects:
        path = root / rel
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError("Candidate0059 performance object missing: " + rel)

    result = {
        "candidate": "0059",
        "performance_source_gate": "PASS",
        "performance_linked_gate": "PASS",
        "config_gate": "PASS",
        "migt_device_source": True,
        "freq_qos_control": True,
        "core_ctl_boost_active": False,
        "thermal_bypass_added": False,
        "global_max_pin_added": False,
        "metis_alias_added": False,
        "iorap_strategy": "defer-outside-c0059",
        "device_runtime_tested": False,
        "jank_fixed": False,
    }
    (root / "candidate-0059-performance-verification.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print("LISA_CANDIDATE_0059_PERFORMANCE_LINKED_GATE=PASS", flush=True)
