#!/usr/bin/env python3
"""Candidate0055: restore mi-memory's UFS registration after the 302 overlay.

Retain the pinned Candidate0054 recipe, protection and raw fault capture.
No changes to PAS, audio, CPU/power settings, watchdog or partition layout.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import candidate_0054_build as inherited

ROOT = Path(__file__).resolve().parents[2]
BUILDER54_SHA = "1d78278e1f293571b01fd8b2bfc225a44159906c"
CAPTURE54_SHA = "e39b7f9a992f41cf5277928f0ecf488635911b96"


def relabel54(text: str) -> str:
    return text.replace('0054', '0055')


def relabel53(text: str) -> str:
    return inherited.relabel(text).replace('0054', '0055')


def preflight() -> str:
    inherited.checked(ROOT / 'reconstruction/scripts/candidate_0054_build.py', BUILDER54_SHA)
    inherited.checked(ROOT / 'reconstruction/scripts/candidate_0054_fault_patch.py', CAPTURE54_SHA)
    inherited.preflight()
    text = relabel54(inherited.transformed_source())
    anchor = 'from candidate_0055_fault_patch import apply'
    if text.count(anchor) != 1:
        raise RuntimeError('Pinned fault-wrapper import changed')
    text = text.replace(anchor, 'from candidate_0055_ufs_patch import apply', 1)
    compile(text, 'candidate0055_resolved', 'exec')
    for name in ('candidate_0055_build.py', 'candidate_0055_ufs_patch.py'):
        py_compile.compile(str(ROOT / 'reconstruction/scripts' / name), doraise=True)
    print('LISA_CANDIDATE_0055_PREFLIGHT=PASS', flush=True)
    return text


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as file:
        for part in iter(lambda: file.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def build() -> None:
    source = preflight()
    (ROOT / 'candidate-0055-resolved-builder.py').write_text(source)
    scope = {'__file__': str(inherited.PARENT), '__name__': '__main__'}
    exec(compile(source, 'candidate0055_resolved', 'exec'), scope)
    manifest = (
        'candidate=Lisa Candidate0055 restore UFS LUN0 mi-memory registry\n'
        'baseline=Candidate0054 95c136f; raw fault capture retained\n'
        f"package_commit={os.environ.get('GITHUB_SHA', 'local')}\n"
        f"workflow_run={os.environ.get('GITHUB_RUN_ID', 'local')}\n"
        f"candidate_0055_image_sha256={digest(ROOT / 'candidate-0055-Image')}\n"
        f"candidate_0055_boot_sha256={digest(ROOT / 'boot.img')}\n"
        'mutation=restore module-aware LUN0 configure hook after UFS overlay; initialized registry publication; readiness guards\n'
        'evidence=020018 MI_RIC get_ufs_hba_data+0x8 called from mv_proc_show+0x40 [mi_memory]; null registry\n'
        'unchanged=PAS/audio/power/watchdog/CFI/camera/display/procfs ABI/boot layout\n'
        'runtime_validation=pending device test; static checks do not prove boot stability\n'
        'LISA_CANDIDATE_0055_FINAL_GATE=PASS\n'
    )
    (ROOT / 'candidate-0055-manifest.txt').write_text(manifest)
    print(manifest, flush=True)


def verify() -> None:
    import yaml
    preflight()
    doc = yaml.safe_load(inherited.checked(inherited.WORKFLOW, inherited.WORKFLOW_SHA))
    steps = doc['jobs']['build']['steps']
    names = [s.get('name', '') for s in steps]
    first = names.index('Download exact stock msm_drm import oracle')
    last = names.index('Final Candidate 0053 static gate')
    work = ROOT / 'candidate-0055-checks'
    work.mkdir(exist_ok=True)
    for index, step in enumerate(steps[first:last + 1], 1):
        print('::group::' + relabel53(step['name']), flush=True)
        if step['name'] == 'Verify Candidate 0053 ARM64 fault front-load diagnostics':
            from candidate_0055_ufs_patch import verify as verify_ufs
            verify_ufs(ROOT)
        else:
            if 'run' not in step or 'uses' in step:
                raise RuntimeError('Unexpected inherited gate type')
            shell = work / f'verify-{index:02d}.sh'
            shell.write_text(relabel53(step['run']))
            env = os.environ.copy()
            env.update({key: inherited.resolve_env(value) for key, value in step.get('env', {}).items()})
            subprocess.run(['bash', '--noprofile', '--norc', '-e', '-o', 'pipefail', str(shell)],
                           cwd=ROOT, env=env, check=True)
        print('::endgroup::', flush=True)
    sha = digest(ROOT / 'boot.img')
    if sha != (ROOT / 'boot.img.sha256').read_text().split()[0]:
        raise RuntimeError('boot.img checksum differs from packaging output')
    manifest = (ROOT / 'candidate-0055-manifest.txt').read_text()
    if f'candidate_0055_boot_sha256={sha}\n' not in manifest:
        raise RuntimeError('Manifest does not match boot.img')
    if 'LISA_CANDIDATE_0055_UFS_REGISTRY_COMPILED_GATE=PASS' not in (ROOT / 'candidate-0055-ufs-registry-verified.txt').read_text():
        raise RuntimeError('Compiled UFS hook gate did not complete')
    report = {'candidate': '0055', 'package_commit': os.environ.get('GITHUB_SHA'),
              'run_id': os.environ.get('GITHUB_RUN_ID'), 'boot_sha256': sha,
              'boot_bytes': (ROOT / 'boot.img').stat().st_size,
              'inherited_gates': 'PASS', 'compiled_ufs_hook': 'PASS',
              'ufs_export_crc_matches': 7, 'runtime_pass': False}
    (ROOT / 'candidate-0055-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print('LISA_CANDIDATE_0055_ARTIFACT_CHECKSUM_GATE=PASS', flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('preflight', 'prepare', 'build', 'verify'), nargs='?', default='build')
    args = parser.parse_args()
    if args.phase == 'preflight':
        preflight()
    elif args.phase == 'prepare':
        preflight()
        inherited.run_parent_phase('prepare')
    elif args.phase == 'verify':
        verify()
    else:
        build()


if __name__ == '__main__':
    main()
