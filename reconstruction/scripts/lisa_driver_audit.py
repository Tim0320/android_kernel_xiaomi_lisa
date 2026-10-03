#!/usr/bin/env python3
"""Read-only, pinned Lisa module-contract audit. Never changes firmware or boot."""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import time
import subprocess
import urllib.request
import zipfile

BASE_ARTIFACT = 11280923629
BASE_ZIP_SHA = '49cbee3283acf4f060772f313d1919c4f5fd4fd8744e53e66128112d9a11e084'
DUMP = 'Jiovanni-dump/xiaomi_lisa_dump'
DUMP_REF = '2dbe7b5569ed49cc2c6649a7b313d4a092755034'
OUT = Path('lisa-driver-audit')
NAMES = {'qti_battery_charger_main_k8.ko', 'qmi_helpers.ko', 'hwid.ko',
         'cnss2.ko', 'icnss2.ko', 'qca_cld3_wlan.ko', 'qca_cld3_qca6750.ko',
         'msm_drm.ko', 'leds-qti-flash.ko', 'mi_thermal_interface.ko',
         'hwkm.ko', 'snd_event_dlkm.ko', 'swr_dlkm.ko', 'q6_pdr_dlkm.ko',
         'rmnet_ctl.ko', 'us_prox_iio.ko'}
PROVIDERS = ['power_debug_print_enabled', 'mi_power_save_battery_cave',
             'get_hw_build_adc', 'qmi_handle_init', 'module_layout']


def get(url):
    error = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Lisa-contract-audit'})
            with urllib.request.urlopen(req, timeout=90) as response:
                data = response.read(50 * 1024 * 1024 + 1)
            if len(data) > 50 * 1024 * 1024:
                raise RuntimeError('Unexpectedly large public file')
            return data
        except (OSError, TimeoutError) as exc:
            error = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise RuntimeError(f'Download failed after retries: {url}: {error}')


def elf_info(data):
    if data[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Expected ELF64 little-endian module')
    shoff = struct.unpack_from('<Q', data, 40)[0]
    entsize, count, names_index = struct.unpack_from('<HHH', data, 58)
    if entsize != 64 or not count or names_index >= count:
        raise ValueError('Unsupported ELF section layout')
    if shoff + entsize * count > len(data):
        raise ValueError('ELF section table out of bounds')
    headers = [struct.unpack_from('<IIQQQQIIQQ', data, shoff + i * entsize)
               for i in range(count)]
    def section(h):
        if h[1] == 8:
            return b''
        off, size = h[4:6]
        if off + size > len(data):
            raise ValueError('ELF section out of bounds')
        return data[off:off + size]
    strings = section(headers[names_index])
    def cstr(buf, off):
        if off >= len(buf):
            raise ValueError('ELF string out of bounds')
        end = buf.find(b'\0', off)
        if end < 0:
            raise ValueError('Unterminated ELF string')
        return buf[off:end].decode('utf-8', errors='replace')
    sections = {cstr(strings, h[0]): section(h) for h in headers}
    fields = {}
    for item in sections.get('.modinfo', b'').split(b'\0'):
        if b'=' in item:
            k, v = item.decode(errors='replace').split('=', 1)
            fields.setdefault(k, []).append(v)
    versions = sections.get('__versions', b'')
    if len(versions) % 64:
        raise ValueError('Unsupported modversion entry size')
    imports = {}
    for offset in range(0, len(versions), 64):
        crc = struct.unpack_from('<Q', versions, offset)[0]
        name = versions[offset + 8:offset + 64].split(b'\0', 1)[0].decode()
        imports[name] = f'0x{crc:08x}'
    exports = []
    for h in headers:
        if h[1] != 2:
            continue
        syms = section(h)
        if h[6] >= count or h[9] != 24 or len(syms) % 24:
            raise ValueError('Invalid symbol table')
        symstrings = section(headers[h[6]])
        for offset in range(0, len(syms), 24):
            name = cstr(symstrings, struct.unpack_from('<I', syms, offset)[0])
            if name.startswith('__ksymtab_'):
                exports.append(name[len('__ksymtab_'):])
    return {'modinfo': fields, 'imports': imports, 'exports': sorted(set(exports))}


def main():
    OUT.mkdir(exist_ok=True)
    repo = os.environ.get('GITHUB_REPOSITORY', 'Tim0320/android_kernel_xiaomi_lisa')
    base = OUT / 'baseline.zip'
    subprocess.run(['curl', '-fL', '--retry', '4', '--retry-all-errors',
        '-H', 'Authorization: Bearer ' + os.environ['GH_TOKEN'],
        '-H', 'Accept: application/vnd.github+json',
        f'https://api.github.com/repos/{repo}/actions/artifacts/{BASE_ARTIFACT}/zip',
        '-o', str(base)], check=True)
    if hashlib.sha256(base.read_bytes()).hexdigest() != BASE_ZIP_SHA:
        raise RuntimeError('Pinned baseline artifact digest mismatch')
    with zipfile.ZipFile(base) as z:
        symvers = z.read('kernel/out/Module.symvers').decode()
        config = z.read('candidate-0055.ikconfig').decode()
        manifest = z.read('candidate-0055-manifest.txt').decode()
        boot_sha = hashlib.sha256(z.read('boot.img')).hexdigest()
        if f'candidate_0055_boot_sha256={boot_sha}\n' not in manifest:
            raise RuntimeError('Baseline boot does not match its manifest')
        (OUT / 'baseline.config').write_text(config)
        (OUT / 'baseline.Module.symvers').write_text(symvers)
    base.unlink()
    built_symbols = {p[1]: {'crc': p[0], 'owner': p[2]} for line in symvers.splitlines()
                     if len(p := line.split()) >= 3}
    symbols = {name: item for name, item in built_symbols.items() if item['owner'] == 'vmlinux'}
    tree = json.loads(get(f'https://api.github.com/repos/{DUMP}/git/trees/{DUMP_REF}?recursive=1'))
    if tree.get('truncated'):
        raise RuntimeError('Public dump tree truncated; refusing incomplete inventory')
    entries = {e['path']: e for e in tree['tree'] if e['type'] == 'blob'}
    selected = [p for p in entries if p.startswith('vendor/lib/modules/')
                and Path(p).name in NAMES]
    if not any(Path(p).name == 'qti_battery_charger_main_k8.ko' for p in selected):
        raise RuntimeError('Pinned public Lisa battery module missing')
    records = []
    for p in sorted(selected):
        data = get(f'https://raw.githubusercontent.com/{DUMP}/{DUMP_REF}/{p}')
        blob_sha = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if blob_sha != entries[p]['sha']:
            raise RuntimeError(f'Public module blob hash mismatch: {p}')
        if data.startswith(b'version https://git-lfs.github.com/spec/v1'):
            match = re.search(rb'oid sha256:([0-9a-f]{64})', data)
            if not match:
                raise RuntimeError('Malformed LFS pointer')
            data = get(f'https://media.githubusercontent.com/media/{DUMP}/{DUMP_REF}/{p}')
            if hashlib.sha256(data).hexdigest() != match.group(1).decode():
                raise RuntimeError(f'Public LFS content hash mismatch: {p}')
        info = elf_info(data)
        info.update(path=p, blob_sha=blob_sha, sha256=hashlib.sha256(data).hexdigest())
        info['missing_from_core'] = sorted(n for n in info['imports'] if n not in symbols)
        info['core_crc_mismatches'] = {n: {'module': crc, 'core': symbols[n]['crc']}
            for n, crc in info['imports'].items() if n in symbols and crc != symbols[n]['crc']}
        info['exports_already_in_core'] = sorted(n for n in info['exports']
            if n in symbols and symbols[n]['owner'] == 'vmlinux')
        records.append(info)
        dest = OUT / 'reference-only' / p
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        print(p, 'missing', len(info['missing_from_core']), 'mismatch',
              len(info['core_crc_mismatches']), 'duplicates', len(info['exports_already_in_core']), flush=True)
    text_paths = [p for p in entries if
        (p.startswith('vendor/lib/modules/') and Path(p).name.startswith('modules.')) or
        p in {'vendor/etc/init/hw/init.qcom.rc', 'vendor/etc/init/hw/init.target.rc',
              'vendor/etc/init/hw/init.qti.kernel.rc', 'vendor/ueventd.rc',
              'vendor/etc/ueventd.rc', 'vendor/bin/init.qcom.wlan.sh',
              'vendor/bin/init.kernel.post_boot-yupik.sh'}]
    for p in text_paths:
        data = get(f'https://raw.githubusercontent.com/{DUMP}/{DUMP_REF}/{p}')
        if b'\0' in data:
            continue
        dest = OUT / 'reference-only' / p
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    header_zip = OUT / 'stock-headers.zip'
    subprocess.run(['curl', '-fL', '--retry', '4', '--retry-all-errors',
        '-H', 'Authorization: Bearer ' + os.environ['GH_TOKEN'],
        '-H', 'Accept: application/vnd.github+json',
        f'https://api.github.com/repos/{repo}/actions/artifacts/10637733529/zip',
        '-o', str(header_zip)], check=True)
    header_matches = []
    with zipfile.ZipFile(header_zip) as z:
        for name in z.namelist():
            if not name.endswith('.h'):
                continue
            body = z.read(name).decode(errors='replace')
            lines = body.splitlines()
            for i, line in enumerate(lines):
                if any(key in line for key in PROVIDERS[:2]):
                    header_matches.append({'path': name, 'line': i + 1,
                        'context': '\n'.join(lines[max(0, i - 2):i + 4])})
    header_digest = hashlib.sha256(header_zip.read_bytes()).hexdigest()
    header_zip.unlink()
    (OUT / 'stock-header-symbols.json').write_text(json.dumps({
        'artifact_id': 10637733529, 'zip_sha256': header_digest,
        'matches': header_matches}, indent=2) + '\n')
    report = {'baseline_commit': '3fa7fb6ba9a65a75d832ca721afb266c6aa8fcdd',
        'baseline_artifact': BASE_ARTIFACT, 'baseline_boot_sha256': boot_sha,
        'reference_dump': DUMP, 'reference_commit': DUMP_REF,
        'reference_is_actual_phone_readback': False,
        'warning': 'Reference ROM is OS2.0.3 global, current reported vendor is OS2.0.8 global. Missing core symbols may be provided by other modules. CRC equality is not runtime ABI proof. Do not force module loading.',
        'core_providers': {n: symbols.get(n) for n in PROVIDERS}, 'modules': records}
    (OUT / 'module-contracts.json').write_text(json.dumps(report, indent=2) + '\n')
    rows = ['# Lisa reference module audit', '', report['warning'], '',
            '| Reference module | Import count | Absent from core | CRC mismatches | Duplicate core exports |',
            '|---|---:|---:|---:|---:|']
    for r in records:
        rows.append(f"| {r['path']} | {len(r['imports'])} | {len(r['missing_from_core'])} | {len(r['core_crc_mismatches'])} | {len(r['exports_already_in_core'])} |")
    rows += ['', '## Required next actions',
        'Confirm the two battery export signatures against stock headers and real call sites before implementing providers. Never return fabricated capacity.',
        'Inspect both normal and 5.4-gki modules.dep and built-in ownership. Fix dependency resolution and real type layouts; never overwrite CRCs to force a load.',
        'Keep display/AOD DAC and SELinux evidence separate from kernel panel functionality. No global permissive mode or chmod 777.',
        'Audit completion is not a repaired boot or a device pass.']
    (OUT / 'REPORT.md').write_text('\n'.join(rows) + '\n')
    print('LISA_DRIVER_CONTRACT_AUDIT_COMPLETE=1')


if __name__ == '__main__':
    main()
