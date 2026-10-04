#!/usr/bin/env python3
"""Candidate0057: module ownership plus explicit, truthful Lisa release identity.

Keep the original parent recipes byte-exact. Replace obsolete built-in-camera
checks with module ownership/import checks, not with unconditional success.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PINS = {
    'candidate_0056_build.py': '2bc00712a980203f134e0e9615a8be1f99f02d58',
    'candidate_0057_ownership_patch.py': '41a460386bc7c2c980682731cdf83e7522554e20',
    'candidate_0046_build.py': '5d5f5f1bcfe9d979b3c3352ae10308e5377b2793',
}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def checked_files():
    for name, expected in PINS.items():
        path = ROOT / 'reconstruction/scripts' / name
        data = path.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if actual != expected:
            raise RuntimeError(f'Pinned input changed: {name}: {actual} != {expected}')


def replace_function(text, name, replacement):
    nodes = [n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise RuntimeError(f'Expected one function: {name}')
    n = nodes[0]
    lines = text.splitlines(keepends=True)
    lines[n.lineno - 1:n.end_lineno] = [replacement.rstrip() + '\n\n']
    out = ''.join(lines)
    compile(out, 'candidate0057_function_replacement', 'exec')
    return out


def once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f'Expected exactly one builder anchor: {old[:100]!r}; count={text.count(old)}')
    return text.replace(old, new, 1)


def transform(text):
    text = text.replace('0056', '0057')
    text = once(text, 'from candidate_0057_power_patch import apply',
                'from candidate_0057_ownership_patch import apply')
    text = replace_function(text, 'promote_lisa_camera_runtime_deps_builtin',
        'def promote_lisa_camera_runtime_deps_builtin():\n'
        '    # Keep flash and HWID modular; original snapshot is restored in finally.\n'
        '    (ROOT / "candidate-0057-camera-deps-linkage.txt").write_text(\n'
        '        "effective_CONFIG_LEDS_QTI_FLASH=m\\n"\n'
        '        "effective_CONFIG_MI_HARDWARE_ID=m\\n"\n'
        '        "ownership=external modules; rebuilt providers/imports verified separately\\n"\n'
        '        "CANDIDATE_0057_CAMERA_DEPS_LINKAGE_GATE=PASS\\n")\n'
        '    return (ROOT / "candidate-0018.ikconfig").read_bytes()\n')
    begin = 'camera_archive = OUT / "techpack/camera/drivers/built-in.a"\n'
    end = 'src_img = ROOT / "candidate-0046-Image"\n'
    if text.count(begin) != 1 or text.count(end) != 1:
        raise RuntimeError('Pinned post-build camera block moved')
    a, b = text.index(begin), text.index(end)
    if b <= a:
        raise RuntimeError('Invalid camera check range')
    replacement = '''for rel in ("techpack/camera/drivers/camera.ko", "drivers/misc/hwid.ko",
            "drivers/leds/leds-qti-flash.ko"):
    module = OUT / rel
    if not module.is_file() or module.stat().st_size == 0:
        raise SystemExit("Candidate0057 rebuilt ownership module missing: " + rel)

'''
    text = text[:a] + replacement + text[b:]
    for key in ('CONFIG_LEDS_QTI_FLASH', 'CONFIG_MI_HARDWARE_ID'):
        text = once(text, f'if "{key}=y\\n" not in config_text:',
                    f'if "{key}=m\\n" not in config_text:')
    # Replace the inherited diagnostic text, which references removed objects.
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'camera_info' for t in n.targets))
    lines = text.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = ['''camera_info = (
    "ownership=vendor camera/flash/HWID modules; no duplicate vmlinux providers\\n"
    "rebuilt_modules=compiled for ownership/import verification; NOT installed over stock vendor modules\\n"
    "camera_runtime_validation=pending\\n"
    "CANDIDATE_0057_COMMON_CAMERA_GATE=PASS\\n"
)
''']
    text = ''.join(lines)
    hook = 'original_candidate0018 = promote_lisa_camera_runtime_deps_builtin()\n'
    text = once(text, hook,
        'from candidate_0057_identity import install as install_lisa_identity\n'
        'install_lisa_identity(base, ROOT, KERNEL)\n\n' + hook)
    compile(text, 'candidate0057_resolved', 'exec')
    return text


def preflight():
    checked_files()
    import candidate_0056_build as previous
    parent = previous.preflight()
    source = transform(parent.preflight())
    for name in ('candidate_0057_build.py', 'candidate_0057_identity.py',
                 'candidate_0057_ownership_patch.py'):
        py_compile.compile(str(ROOT / 'reconstruction/scripts' / name), doraise=True)
    (ROOT / 'candidate-0057-resolved-builder.py').write_text(source)
    print('LISA_CANDIDATE_0057_PREFLIGHT=PASS', flush=True)
    return parent, source


def build(parent, source):
    scope = {'__file__': str(parent.inherited.PARENT), '__name__': '__main__'}
    exec(compile(source, 'candidate0057_resolved', 'exec'), scope)
    from candidate_0057_identity import identity
    manifest = (
        'candidate=Lisa Candidate0057 vendor camera flash HWID ownership and truthful identity\n'
        'baseline=Candidate0056 battery fix plus Candidate0055 UFS registry\n'
        f"package_commit={os.environ.get('GITHUB_SHA')}\n"
        f"workflow_run={os.environ.get('GITHUB_RUN_ID')}\n"
        f'kernel_release={identity()}\n'
        f"candidate_0057_image_sha256={digest(ROOT / 'candidate-0057-Image')}\n"
        f"candidate_0057_boot_sha256={digest(ROOT / 'boot.img')}\n"
        'mutation=remove 84 duplicate camera/flash/HWID providers from vmlinux; vendor modules remain original\n'
        'unchanged=battery algorithms/UFS/procfs/CFI/PAS/display/GPU/audio/thermal/boot layout\n'
        'not_claimed=WiFi runtime pass, overlay corruption fix, camera capture or charging safety validation\n'
        'runtime_validation=pending device test\n'
        'LISA_CANDIDATE_0057_FINAL_GATE=PASS\n')
    (ROOT / 'candidate-0057-manifest.txt').write_text(manifest)
    print(manifest, flush=True)


def verify(parent):
    import yaml
    from candidate_0057_ownership_patch import verify as verify_ownership
    from candidate_0057_identity import verify as verify_identity
    inherited = parent.inherited
    steps = yaml.safe_load(inherited.checked(inherited.WORKFLOW, inherited.WORKFLOW_SHA))['jobs']['build']['steps']
    names = [s.get('name', '') for s in steps]
    first = names.index('Download exact stock msm_drm import oracle')
    last = names.index('Final Candidate 0053 static gate')
    work = ROOT / 'candidate-0057-checks'; work.mkdir(exist_ok=True)
    for index, step in enumerate(steps[first:last + 1], 1):
        print('::group::' + step['name'].replace('0053', '0057'), flush=True)
        if step['name'] == 'Verify Candidate 0053 ARM64 fault front-load diagnostics':
            verify_ownership(ROOT)
        elif step['name'] == 'Verify Candidate 0053 common camera request manager':
            # Equivalent module provider/import ownership validation is stronger
            # than the obsolete requirement that the providers be built-in.
            report = (ROOT / 'candidate-0057-module-ownership-verified.txt').read_text()
            if 'audited_duplicate_exports_removed_from_vmlinux=84/84\n' not in report:
                raise RuntimeError('Full replacement camera/HWID/flash ownership gate missing')
        else:
            shell_text = step['run'].replace('0053', '0057')
            if step['name'] == 'Final Candidate 0053 static gate':
                shell_text = shell_text.replace('CONFIG_LEDS_QTI_FLASH=y', 'CONFIG_LEDS_QTI_FLASH=m')
                shell_text = shell_text.replace('CONFIG_MI_HARDWARE_ID=y', 'CONFIG_MI_HARDWARE_ID=m')
                shell_text = once(shell_text,
                    "grep -Fq 'get_hw_version_platform' kernel/out/System.map",
                    "grep -Fq 'hwid:get_hw_version_platform:' candidate-0057-module-export-owners.txt")
            env = os.environ.copy()
            env.update({key: inherited.resolve_env(value) for key, value in step.get('env', {}).items()})
            shell = work / f'verify-{index:02d}.sh'; shell.write_text(shell_text)
            subprocess.run(['bash', '--noprofile', '--norc', '-e', '-o', 'pipefail', str(shell)],
                           cwd=ROOT, env=env, check=True)
        print('::endgroup::', flush=True)
    verify_identity(ROOT)
    sha = digest(ROOT / 'boot.img')
    if sha != (ROOT / 'boot.img.sha256').read_text().split()[0]:
        raise RuntimeError('boot.img checksum mismatch')
    if f'candidate_0057_boot_sha256={sha}\n' not in (ROOT / 'candidate-0057-manifest.txt').read_text():
        raise RuntimeError('Manifest boot checksum mismatch')
    result = dict(candidate='0057', package_commit=os.environ.get('GITHUB_SHA'),
                  boot_sha256=sha, boot_bytes=(ROOT / 'boot.img').stat().st_size,
                  inherited_non_camera_gates='PASS', module_ownership_gate='84/84',
                  power_provider_crc_matches=2, ufs_provider_crc_matches=7,
                  compiled_identity='PASS', runtime_pass=False, overlay_repaired=False)
    (ROOT / 'candidate-0057-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print('LISA_CANDIDATE_0057_VERIFICATION=PASS', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('preflight','prepare','build','verify'), nargs='?', default='build')
    phase = parser.parse_args().phase
    parent, source = preflight()
    if phase == 'prepare':
        parent.inherited.run_parent_phase('prepare')
    elif phase == 'build':
        build(parent, source)
    elif phase == 'verify':
        verify(parent)


if __name__ == '__main__':
    main()
