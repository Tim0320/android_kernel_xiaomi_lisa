#!/usr/bin/env python3
"""Read-only second-stage Lisa camera/HWID/WLAN ownership audit."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile
from lisa_driver_audit import get, elf_info, DUMP, DUMP_REF

OUT = Path('lisa-camera-wlan-audit')
AUDIT_ARTIFACT = 11282054888
AUDIT_SHA = '8e25c7d93bf7ba7b505f9b1e5771aae448df7be3e0597eb99c13545204eaa9f6'
SOURCE_REF = '6e568aabc77a06fa787baec1d9e60e4b559874a3'
SOURCE_PATHS = (
    'drivers/misc/hwid.c', 'include/linux/hwid.h',
    'techpack/camera/Makefile', 'techpack/camera/drivers/Makefile',
    'techpack/camera/config/yupikcamera.conf',
    'techpack/camera/config/lahainacamera.conf',
    'techpack/camera/drivers/cam_utils/cam_soc_util.c',
    'techpack/camera/drivers/cam_sensor_module/cam_csiphy/cam_csiphy_core.c',
)


def main():
    OUT.mkdir(exist_ok=True)
    repo = os.environ.get('GITHUB_REPOSITORY', 'Tim0320/android_kernel_xiaomi_lisa')
    archive = OUT / 'previous-audit.zip'
    subprocess.run(['curl', '-fL', '--retry', '4', '--retry-all-errors',
        '-H', 'Authorization: Bearer ' + os.environ['GH_TOKEN'],
        '-H', 'Accept: application/vnd.github+json',
        f'https://api.github.com/repos/{repo}/actions/artifacts/{AUDIT_ARTIFACT}/zip',
        '-o', str(archive)], check=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != AUDIT_SHA:
        raise RuntimeError('Previous audit digest mismatch')
    with zipfile.ZipFile(archive) as z:
        previous = json.loads(z.read('module-contracts.json'))
        core = {p[1]: p[0] for raw in z.read('baseline.Module.symvers').decode().splitlines()
                if len(p := raw.split()) >= 3 and p[2] == 'vmlinux'}
    archive.unlink()
    records = {Path(item['path']).stem: item for item in previous['modules']
               if '/5.4-gki/' not in item['path']}
    tree = json.loads(get(f'https://api.github.com/repos/{DUMP}/git/trees/{DUMP_REF}?recursive=1'))
    if tree.get('truncated'):
        raise RuntimeError('Reference tree is incomplete')
    blobs = {item['path']: item['sha'] for item in tree['tree'] if item['type'] == 'blob'}
    missing_files = []
    todo = ['camera', 'cnss2', 'icnss2', 'qca_cld3_wlan', 'qca_cld3_qca6750']
    visited = set()
    while todo:
        name = todo.pop()
        if name in visited:
            continue
        visited.add(name)
        if len(visited) > 128:
            raise RuntimeError('Unexpectedly large dependency closure')
        if name not in records:
            path = f'vendor/lib/modules/{name}.ko'
            if path not in blobs:
                missing_files.append(path)
                continue
            data = get(f'https://raw.githubusercontent.com/{DUMP}/{DUMP_REF}/{path}')
            blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if blob != blobs[path]:
                raise RuntimeError('Reference module hash mismatch: ' + path)
            if data.startswith(b'version https://git-lfs.github.com/spec/v1'):
                expected = re.search(rb'oid sha256:([a-f0-9]{64})', data)
                if expected is None:
                    raise RuntimeError('Invalid LFS pointer')
                data = get(f'https://media.githubusercontent.com/media/{DUMP}/{DUMP_REF}/{path}')
                if hashlib.sha256(data).hexdigest() != expected.group(1).decode():
                    raise RuntimeError('Reference LFS hash mismatch')
            rec = elf_info(data)
            rec.update(path=path, sha256=hashlib.sha256(data).hexdigest())
            records[name] = rec
            target = OUT / 'reference-only' / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for item in records[name]['modinfo'].get('depends', []):
            todo.extend(dep for dep in item.split(',') if dep)
    export_owners = {}
    for name, record in records.items():
        for symbol in record['exports']:
            export_owners.setdefault(symbol, []).append(name)
    report = []
    for name in sorted(visited & records.keys()):
        record = records[name]
        report.append({
            'name': name, 'path': record['path'], 'modinfo': record['modinfo'],
            'sha256': record['sha256'], 'imports': record['imports'],
            'core_crc_mismatches': {n: {'module': c, 'core': core[n]}
                for n, c in record['imports'].items() if n in core and c != core[n]},
            'duplicate_core_exports': [n for n in record['exports'] if n in core],
            'non_core_import_owners': {n: export_owners.get(n, [])
                for n in record['imports'] if n not in core},
        })
    contexts = []
    for path in SOURCE_PATHS:
        data = get(f'https://raw.githubusercontent.com/{repo}/{SOURCE_REF}/{path}')
        text = data.decode()
        target = OUT / 'reference-source' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.search(r'get_hw_version|CONFIG_SPECTRA_CAMERA|CONFIG_MI_HARDWARE_ID|CONFIG_LEDS_QTI_FLASH', line):
                contexts.append({'path': path, 'line': i + 1,
                    'source_sha256': hashlib.sha256(data).hexdigest(),
                    'context': '\n'.join(lines[max(0, i - 3):i + 5])})
    result = {'reference_commit': DUMP_REF, 'source_commit': SOURCE_REF,
        'baseline_commit': previous['baseline_commit'], 'modules': report,
        'missing_dependency_files': sorted(set(missing_files)), 'source_context': contexts,
        'limits': 'Public OS2.0.3 modules, not actual OS2.0.8 phone bytes. Core CRC matching is not runtime ABI proof. Export ownership of other modules is identified by names, not asserted type/layout compatibility. Source scan covers only the listed eight files.',
        'purpose': 'Evaluate coherent stock camera/flash/HWID module ownership before changing WIFI dependencies. No boot or kernel is changed.'}
    (OUT / 'ownership.json').write_text(json.dumps(result, indent=2) + '\n')
    rows = ['# Lisa camera/HWID/WLAN ownership', '', result['limits'], '',
            '| Module | Core CRC mismatch | Duplicate core exports | Unresolved symbol names in this reference set |',
            '|---|---:|---:|---:|']
    for item in report:
        rows.append(f"| {item['name']} | {len(item['core_crc_mismatches'])} | {len(item['duplicate_core_exports'])} | {sum(not v for v in item['non_core_import_owners'].values())} |")
    rows += ['', 'Missing dependency files: ' + repr(result['missing_dependency_files']), '',
        'Do not overwrite CRCs, bypass module verification, or treat missing optional debug output as a proven root cause.',
        'A candidate restoring camera/flash/HWID modular ownership needs explicit replacement of built-in-camera gates by module import/ownership gates; do not silently skip them.',
        'Power providers from Candidate0056 must be independently verified before using them to unblock the camera -> flash -> battery chain.']
    (OUT / 'REPORT.md').write_text('\n'.join(rows) + '\n')
    print('LISA_CAMERA_WLAN_OWNERSHIP_AUDIT=COMPLETE', flush=True)


if __name__ == '__main__':
    main()
