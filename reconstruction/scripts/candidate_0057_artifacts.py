#!/usr/bin/env python3
"""Save unverified build outputs before verification; restore without compiling.

Only explicit generated files are archived. No checkout credentials, environment
files or user device logs enter the checkpoint. Reuse requires identical build
inputs; a verifier-only update must not relabel the original compiled kernel.
"""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = 'lisa-build-checkpoint.json'
WARNING = 'UNVERIFIED-DO-NOT-FLASH.txt'
WARNING_TEXT = ('UNVERIFIED BUILD OUTPUT - NOT AN APPROVED FLASH IMAGE\n'
                'Saving this artifact does not mean verification passed.\n'
                'Use the separately published verified artifact after all gates pass.\n'
                'Static checks are not a hardware/runtime pass.\n')
REQUIRED = (
    'boot.img', 'boot.img.sha256', 'candidate-0057-Image', 'candidate-0046-Image',
    'candidate-0057.config', 'candidate-0057.ikconfig', 'candidate-0046.config',
    'candidate-0046.ikconfig', 'candidate-0057-identity.json', 'candidate-0057-manifest.txt',
    'kernel/out/.config', 'kernel/out/System.map', 'kernel/out/Module.symvers',
    'kernel/out/include/generated/utsrelease.h', 'kernel/out/include/generated/compile.h',
    'kernel/out/kernel/power/lisa_power_compat.o',
    'kernel/out/techpack/camera/drivers/camera.ko', 'kernel/out/drivers/misc/hwid.ko',
    'kernel/out/drivers/leds/leds-qti-flash.ko',
    'kernel/out/techpack/display/msm/msm_drm.ko',
    'kernel/out/techpack/display/msm/modules.order',
    'kernel/out/techpack/display/msm/built-in.a',
    'kernel/kernel/module.c', 'kernel/arch/arm64/mm/fault.c',
    'kernel/drivers/mtd/mtdoops.c', 'kernel/drivers/soc/qcom/subsys-pil-tz.c',
    'kernel/drivers/soc/qcom/peripheral-loader.c', 'kernel/drivers/firmware/qcom_scm.c',
    'kernel/drivers/scsi/ufs/ufshcd.c', 'kernel/drivers/misc/mi-memory/mem_interface.c',
    'kernel/drivers/gpu/msm/adreno-gpulist.h', 'kernel/include/linux/rwsem.h',
    'kernel/include/linux/proc_fs.h', 'kernel/fs/proc/generic.c',
    'kernel/include/linux/soc/qcom/battery_charger.h',
    'kernel/arch/arm64/boot/dts/vendor/qcom/yupik.dtsi',
    'kernel/arch/arm64/boot/dts/vendor/qcom/yupik-gpu.dtsi',
    'kernel/techpack/display/config/lahainadisp.conf',
    'kernel/techpack/camera/config/yupikcamera.conf',
    'kernel/techpack/camera/config/lahainacamera.conf',
    'kernel/techpack/camera/drivers/cam_sensor_module/cam_flash/cam_flash_dev.h',
    '.lisa-reference-0057/leds-qti-flash.ko',
    '.lisa-reference-0057/qti_battery_charger_main_k8.ko',
)
OPTIONAL = ('kernel/out/vmlinux', 'clang-version.txt',
            'stock-msm-drm-imports.tsv', 'stock-msm-drm-summary.tsv')
RECIPE_PARTS = {
    'candidate_0057_build.py': {'PINS', 'checked_files', 'transform', 'build', 'once', 'replace_function', 'digest'},
    'candidate_0057_identity.py': {'identity', 'set_config', 'check_loader', 'install'},
}


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def recipe_fingerprint(root):
    entries = {}
    scripts = root / 'reconstruction/scripts'
    for path in sorted(scripts.glob('candidate_00*.py')):
        # These are never used to generate kernel/boot bytes.
        if path.name in ('candidate_0057_artifacts.py', 'candidate_0057_flash_contract.py'):
            continue
        if path.name in RECIPE_PARTS:
            wanted = RECIPE_PARTS[path.name]
            nodes = []
            found = set()
            for node in ast.parse(path.read_text()).body:
                name = getattr(node, 'name', None)
                if isinstance(node, ast.Assign):
                    names = {t.id for t in node.targets if isinstance(t, ast.Name)}
                    if wanted & names:
                        found.update(wanted & names); nodes.append(ast.dump(node))
                elif name in wanted:
                    found.add(name); nodes.append(ast.dump(node))
            if found != wanted:
                raise RuntimeError('Build fingerprint function/constant missing: ' + path.name)
            entries[str(path.relative_to(root))] = hashlib.sha256('\n'.join(nodes).encode()).hexdigest()
        else:
            entries[str(path.relative_to(root))] = sha256(path)
    for name in RECIPE_PARTS:
        if 'reconstruction/scripts/' + name not in entries:
            raise RuntimeError('Build fingerprint recipe missing: ' + name)
    for path in sorted((root / 'reconstruction/overlays').glob('*')):
        if path.is_file():
            entries[str(path.relative_to(root))] = sha256(path)
    workflow = root / '.github/workflows/build-lisa-candidate-0053-arm64-fault-capture.yml'
    entries[str(workflow.relative_to(root))] = sha256(workflow)
    # Check source checkout pins/toolchain/compile environment, not verify steps.
    import yaml
    active = root / '.github/workflows/build-lisa-candidate-0057-ownership-identity.yml'
    steps = yaml.safe_load(active.read_text())['jobs']['build']['steps']
    build_ids = {'kernel_source', 'runtime_reference', 'toolchain', 'compile'}
    selected = [s for s in steps if s.get('id') in build_ids]
    if {s.get('id') for s in selected} != build_ids:
        raise RuntimeError('Build workflow fingerprint inputs missing')
    entries['build-workflow-inputs'] = hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def allowed(name):
    if name in REQUIRED or name in OPTIONAL:
        return True
    return bool(re.fullmatch(r'candidate-[0-9]{4}[-.][A-Za-z0-9_.-]+\.(?:txt|json|log|patch|config|ikconfig)', name)
                or re.fullmatch(r'candidate-[0-9]{4}\.(?:config|ikconfig)', name)
                or re.fullmatch(r'candidate-[0-9]{4}-resolved-builder\.py', name))


def checked_local(root, name):
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise RuntimeError('Missing or unsafe checkpoint input: ' + name)
    return path


def collect(root):
    for name in REQUIRED:
        p = checked_local(root, name)
        if not p.stat().st_size:
            raise RuntimeError('Empty checkpoint input: ' + name)
    names = set(REQUIRED)
    names.update(n for n in OPTIONAL if (root / n).is_file())
    names.update(p.name for p in root.glob('candidate-*') if p.is_file() and allowed(p.name))
    # A cached verification result is not proof that this attempt passed.
    names.discard('candidate-0057-verification.json')
    return sorted(names)


def save(root, archive):
    commit, run = os.environ.get('GITHUB_SHA', ''), os.environ.get('GITHUB_RUN_ID', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or not run.isdecimal():
        raise RuntimeError('Exact build commit/run identity required')
    names = collect(root)
    record = dict(schema=1, candidate='0057', state='UNVERIFIED', runtime_pass=False,
                  build_commit=commit, build_run_id=run,
                  build_attempt=os.environ.get('GITHUB_RUN_ATTEMPT', '1'),
                  recipe_fingerprint=recipe_fingerprint(root), files={})
    for name in names:
        path = checked_local(root, name)
        record['files'][name] = {'bytes': path.stat().st_size, 'sha256': sha256(path)}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, 'w:gz', compresslevel=1, dereference=True) as tar:
        for name in names:
            tar.add(root / name, arcname=name, recursive=False)
        for name, raw in ((MANIFEST, (json.dumps(record, sort_keys=True, indent=2)+'\n').encode()),
                          (WARNING, WARNING_TEXT.encode())):
            info = tarfile.TarInfo(name); info.size = len(raw); info.mode = 0o644
            tar.addfile(info, io.BytesIO(raw))
    (root / MANIFEST).write_text(json.dumps(record, sort_keys=True, indent=2)+'\n')
    (root / WARNING).write_text(WARNING_TEXT)
    (archive.parent / (archive.name + '.sha256')).write_text(sha256(archive)+'  '+archive.name+'\n')
    print(f'CHECKPOINT_SAVED_UNVERIFIED files={len(names)} bytes={archive.stat().st_size}', flush=True)


def restore(root, archive, expected_commit, expected_run):
    if not re.fullmatch(r'[0-9a-f]{40}', expected_commit) or not str(expected_run).isdecimal():
        raise RuntimeError('Expected source commit/run required')
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)):
            raise RuntimeError('Duplicate checkpoint paths')
        for item in members:
            path = PurePosixPath(item.name)
            if not item.isfile() or path.is_absolute() or '..' in path.parts or '\\' in item.name:
                raise RuntimeError('Unsafe checkpoint path/type: ' + item.name)
            if item.name not in (MANIFEST, WARNING) and not allowed(item.name):
                raise RuntimeError('Unexpected checkpoint path: ' + item.name)
        info = tar.getmember(MANIFEST)
        if info.size > 2 * 1024 * 1024:
            raise RuntimeError('Oversized checkpoint manifest')
        record = json.load(tar.extractfile(info))
        if (record.get('schema'), record.get('candidate'), record.get('state')) != (1, '0057', 'UNVERIFIED'):
            raise RuntimeError('Unsupported checkpoint schema/state')
        if record.get('build_commit') != expected_commit or record.get('build_run_id') != str(expected_run):
            raise RuntimeError('Checkpoint source identity mismatch')
        if record.get('recipe_fingerprint') != recipe_fingerprint(root):
            raise RuntimeError('Kernel/build recipe changed; full rebuild required')
        if not set(REQUIRED).issubset(record['files']):
            raise RuntimeError('Incomplete verification checkpoint')
        if set(names) != set(record['files']) | {MANIFEST, WARNING}:
            raise RuntimeError('Checkpoint inventory mismatch')
        # Validate every payload before writing anything into the working tree.
        for name, expected in record['files'].items():
            entry = tar.getmember(name)
            if entry.size != expected['bytes']:
                raise RuntimeError('Checkpoint size mismatch: ' + name)
            h = hashlib.sha256()
            with tar.extractfile(entry) as src:
                for chunk in iter(lambda: src.read(1024 * 1024), b''):
                    h.update(chunk)
            if h.hexdigest() != expected['sha256']:
                raise RuntimeError('Checkpoint hash mismatch: ' + name)
        for item in members:
            target = root / item.name
            if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
                raise RuntimeError('Unsafe checkpoint destination: ' + item.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(item) as src, target.open('wb') as dst:
                for chunk in iter(lambda: src.read(1024 * 1024), b''):
                    dst.write(chunk)
    env = os.environ.get('GITHUB_ENV')
    if env:
        with open(env, 'a') as f:
            f.write('LISA_BUILD_COMMIT='+expected_commit+'\nLISA_BUILD_RUN_ID='+str(expected_run)+'\n')
    print('CHECKPOINT_RESTORED_UNVERIFIED source='+expected_commit[:7]+'; no compilation performed', flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('phase', choices=('save', 'restore'))
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--commit'); p.add_argument('--run')
    args = p.parse_args()
    if args.phase == 'save':
        save(ROOT, args.archive)
    else:
        restore(ROOT, args.archive, args.commit or '', args.run or '')


if __name__ == '__main__':
    main()
