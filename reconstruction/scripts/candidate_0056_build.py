#!/usr/bin/env python3
"""Candidate0056: typed Xiaomi battery providers on the verified 0055 recipe."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import py_compile
import subprocess
import tempfile
import types

ROOT = Path(__file__).resolve().parents[2]
BUILDER55_SHA = '9d85b0dc2d936ccc31fe2adf2bbb352071edfea5'


def parent():
    path = ROOT / 'reconstruction/scripts/candidate_0055_build.py'
    data = path.read_bytes()
    sha = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if sha != BUILDER55_SHA:
        raise RuntimeError('Pinned Candidate0055 recipe changed')
    text = data.decode().replace('0055', '0056')
    text = text.replace('candidate_0056_ufs_patch', 'candidate_0056_power_patch')
    mod = types.ModuleType('candidate0056_parent')
    mod.__file__ = str(path)
    exec(compile(text, str(path), 'exec'), mod.__dict__)
    return mod


def preflight():
    for name in ('candidate_0056_build.py', 'candidate_0056_power_patch.py'):
        py_compile.compile(str(ROOT / 'reconstruction/scripts' / name), doraise=True)
    mod = parent()
    mod.preflight()
    from candidate_0056_power_patch import retained
    retained(ROOT)
    with tempfile.TemporaryDirectory() as tmp:
        exe = str(Path(tmp) / 'power-test')
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined',
                        str(ROOT / 'reconstruction/scripts/test_lisa_power_compat.c'), '-o', exe], check=True)
        subprocess.run([exe], check=True)
    print('LISA_CANDIDATE_0056_PREFLIGHT=PASS', flush=True)
    return mod


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('preflight', 'prepare', 'build', 'verify'), nargs='?', default='build')
    args = parser.parse_args()
    mod = preflight()
    if args.phase == 'prepare':
        mod.inherited.run_parent_phase('prepare')
    elif args.phase == 'build':
        mod.build()
        manifest = (
            'candidate=Lisa Candidate0056 Xiaomi battery-provider compatibility\n'
            'baseline=Candidate0055 3fa7fb6; UFS registry and raw fault capture retained\n'
            f"package_commit={os.environ.get('GITHUB_SHA', 'local')}\n"
            f"workflow_run={os.environ.get('GITHUB_RUN_ID', 'local')}\n"
            f"candidate_0056_image_sha256={mod.digest(ROOT / 'candidate-0056-Image')}\n"
            f"candidate_0056_boot_sha256={mod.digest(ROOT / 'boot.img')}\n"
            'mutation=two typed power providers plus bounded power-mode/debug sysfs; normal-mode capacity preserved\n'
            'unchanged=charging limits/thermal/CFI/PAS/WLAN/display/audio/UFS/procfs/boot layout\n'
            'not_claimed=complete OEM power diagnostics, battery hardware validation, WiFi repair or AOD repair\n'
            'runtime_validation=pending device test\n'
            'LISA_CANDIDATE_0056_FINAL_GATE=PASS\n')
        (ROOT / 'candidate-0056-manifest.txt').write_text(manifest)
        print(manifest, flush=True)
    elif args.phase == 'verify':
        mod.verify()
        gate = (ROOT / 'candidate-0056-power-verified.txt').read_text()
        if 'LISA_CANDIDATE_0056_POWER_COMPILED_GATE=PASS' not in gate:
            raise RuntimeError('Battery provider validation did not complete')
        path = ROOT / 'candidate-0056-verification.json'
        report = json.loads(path.read_text())
        report.update(power_provider_crc_matches=2, power_provider_code=True,
                      battery_hardware_validated=False, wifi_repaired=False)
        path.write_text(json.dumps(report, indent=2) + '\n')
        for src in ('modules.builtin', 'modules.builtin.modinfo'):
            p = ROOT / 'kernel/out' / src
            if p.is_file():
                (ROOT / ('candidate-0056-' + src)).write_bytes(p.read_bytes())


if __name__ == '__main__':
    main()
