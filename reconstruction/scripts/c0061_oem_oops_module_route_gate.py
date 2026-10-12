#!/usr/bin/env python3
"""Read-only correlation of C0061 OEM Oops record and OEM QGKI/GKI manifests.

No Android access, partition writes, or copyrighted vendor loader redistribution.
Never treats a static manifest as the device's first modprobe -l ordering.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
import zipfile

OOPS_MEMBER = r"pulled\block_partitions\lisa_oops_iter0001.bin"
OOPS_MAGIC = bytes.fromhex('005d005d')
CHUNK_BYTES = 2 * 1024 * 1024
MAX_OOPS_BYTES = 128 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024
KERNEL = re.compile(r"5\.4\.302-qgki-lisa-c0061-[A-Za-z0-9-]+")
TIME = re.compile(r"\[\s*(\d+\.\d+)\]")
MODULE_MARKER = re.compile(r"LISA0054_MODULE name=([A-Za-z0-9_]+)")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def member(z: zipfile.ZipFile, path: str) -> bytes:
    info = z.getinfo(path)
    if info.file_size > MAX_MEMBER_BYTES:
        raise ValueError('refusing excessive ZIP member size')
    return z.read(info)


def dep_names(z: zipfile.ZipFile, path: str) -> set[str]:
    rows = member(z, path).decode('utf-8').splitlines()
    names = []
    for row in rows:
        if ':' not in row or row.startswith('#'):
            continue
        p = row.split(':', 1)[0].strip().rsplit('/', 1)[-1]
        if not p.endswith('.ko'):
            raise ValueError('unexpected manifest item: ' + p)
        names.append(p[:-3].replace('-', '_'))
    if len(names) != len(set(names)) or len(names) == 0:
        raise ValueError('duplicate/empty dependency manifest')
    return set(names)


def validated_records(data: bytes) -> list[bytes]:
    if not data or len(data) > MAX_OOPS_BYTES:
        raise ValueError('OEM Oops size outside allowed range')
    if len(data) % CHUNK_BYTES:
        raise ValueError('unexpected OEM Oops storage geometry')
    pieces = [data[i:i+CHUNK_BYTES] for i in range(0, len(data), CHUNK_BYTES)]
    for i, part in enumerate(pieces):
        if part[4:8] != OOPS_MAGIC:
            raise ValueError(f'unknown OEM Oops header at record {i}; fail closed')
    return pieces


def split_clock_segments(text: str) -> list[str]:
    """MTDOOPS can prepend old tail snapshots; split at boot-relative clock resets."""
    groups: list[list[str]] = [[]]
    previous = None
    for line in text.splitlines():
        t = re.match(r"^<\d+>\[\s*(\d+\.\d+)\]", line)
        if t:
            cur = float(t.group(1))
            if previous is not None and previous - cur > 5.0:
                groups.append([])
            previous = cur
        groups[-1].append(line)
    return ['\n'.join(g) for g in groups]


def parse_segment(text: str, qgki: set[str], gki: set[str]) -> dict:
    panic_present = 'Kernel panic - not syncing:' in text
    nfc_panic_correlated = all(token in text for token in (
        'Kernel panic - not syncing:', 'nfc_dev_open', 'nqnfcinfo'))
    lines = text.splitlines()
    panic_line = next((i for i, line in enumerate(lines) if 'Kernel panic - not syncing:' in line), None)
    # Select the LAST nonempty Modules-linked-in line before the panic.
    active_names = set()
    active_time = None
    if panic_line is not None:
        for line in lines[:panic_line]:
            if 'Modules linked in:' not in line:
                continue
            tail = line.split('Modules linked in:', 1)[1].strip()
            if not tail:
                continue
            active_names = {n.split('(')[0].replace('-', '_') for n in tail.split()}
            t = TIME.search(line)
            active_time = float(t.group(1)) if t else None
    loaded_markers = set()
    loaded_stamps = {}
    for line in lines:
        m = MODULE_MARKER.search(line)
        if m:
            name = m.group(1)
            loaded_markers.add(name)
            time = TIME.search(line)
            if time and name not in loaded_stamps:
                loaded_stamps[name] = float(time.group(1))
    q_only = qgki - gki
    g_only = gki - qgki
    def sorted_hits(s):
        return sorted(s)
    q_only_active = sorted_hits(active_names & q_only)
    g_only_active = sorted_hits(active_names & g_only)
    q_only_markers = sorted_hits(loaded_markers & q_only)
    g_only_markers = sorted_hits(loaded_markers & g_only)
    first_q_only = min(((t,n) for n,t in loaded_stamps.items() if n in q_only),default=(None, None))
    first_nfc = loaded_stamps.get('nfc_i2c')
    probe_line = next((line for line in lines if 'nfc_i2c_dev_probe success' in line), None)
    probe_t = TIME.search(probe_line) if probe_line else None
    panic_t = TIME.search(lines[panic_line]) if panic_line is not None else None
    kernel_releases = sorted(set(KERNEL.findall(text)))
    first_stage_hwkm = any('/lib/modules/5.4-gki/hwkm.ko' in line for line in lines)
    audio_modprobe_failure = any("Service 'exec 2 (/vendor/bin/modprobe -a -d /vendor/lib/modules" in line
                                  and 'exited with status 1' in line for line in lines)
    # This is a correlation of two independent manifestations of the same
    # QGKI-only module family; never assert a specific modprobe first probe.
    if not nfc_panic_correlated:
        route = 'NO_CORRELATED_NFC_PANIC'
    elif len(q_only_active) >= 10 and len(q_only_markers) >= 10 and not g_only_active and not g_only_markers:
        route = 'STRONG_QGKI_LOADED_SET_CORRELATION_NOT_LOADER_ATTESTATION'
    else:
        route = 'INCONCLUSIVE'
    return {
        'kernel_releases': kernel_releases,
        'panic_present': panic_present,
        'nfc_panic_correlated_within_record': nfc_panic_correlated,
        'route_inference': route,
        'active_modules_total': len(active_names),
        'active_modules_qgki_only': len(q_only_active),
        'active_modules_gki_only': len(g_only_active),
        'active_qgki_only_names': q_only_active,
        'active_gki_only_names': g_only_active,
        'loaded_marker_modules_total': len(loaded_markers),
        'loaded_markers_qgki_only': len(q_only_markers),
        'loaded_markers_gki_only': len(g_only_markers),
        'first_qgki_only_marker': {'module': first_q_only[1], 'seconds': first_q_only[0]},
        'nfc_module_marker_seconds': first_nfc,
        'nfc_probe_success_seconds': float(probe_t.group(1)) if probe_t else None,
        'panic_seconds': float(panic_t.group(1)) if panic_t else None,
        'active_list_seconds': active_time,
        'first_stage_gki_hwkm_attempt': first_stage_hwkm,
        'separate_init_audio_modprobe_exit_1': audio_modprobe_failure,
        'nfc_exact_binary_origin': 'UNKNOWN',
        'oem_vendor_modprobe_first_probe': 'UNKNOWN',
        'actual_future_blacklist_variant_behavior': 'UNKNOWN',
        'flash_authorized': False,
    }


def parse_record(record: bytes, qgki: set[str], gki: set[str]) -> dict:
    parts = split_clock_segments(record.decode('utf-8', 'replace'))
    assessed = [parse_segment(part, qgki, gki) for part in parts]
    panic = [(i,r) for i,r in enumerate(assessed) if r['nfc_panic_correlated_within_record']]
    if len(panic) != 1:
        return {
            'record_segment_count': len(parts),
            'panic_segment_index': None,
            'nfc_panic_correlated_within_record': False,
            'route_inference': 'AMBIGUOUS_OR_ABSENT_SAME_CLOCK_SEGMENT_PANIC',
        }
    idx,r = panic[0]
    r['record_segment_count'] = len(parts)
    r['panic_segment_index'] = idx
    return r


def run(oops_zip: Path, module_zip: Path) -> dict:
    with zipfile.ZipFile(module_zip) as z:
        if z.testzip() is not None:
            raise ValueError('module ZIP CRC failure')
        qgki = dep_names(z, 'lib/modules/modules.dep')
        gki = dep_names(z, 'lib/modules/5.4-gki/modules.dep')
    with zipfile.ZipFile(oops_zip) as z:
        if z.testzip() is not None:
            raise ValueError('oops ZIP CRC failure')
        raw = member(z, OOPS_MEMBER)
    records = validated_records(raw)
    analyzed = [(i, parse_record(rec, qgki, gki)) for i, rec in enumerate(records)]
    matching = [(i, r) for i,r in analyzed if r['nfc_panic_correlated_within_record']]
    if len(matching) == 1:
        idx, record = matching[0]
        result_type = record['route_inference']
    elif len(matching) > 1:
        idx, record = None, None
        result_type = 'MULTIPLE_PANIC_RECORDS_CANNOT_SELECT_FIRST_FAULT'
    else:
        idx, record = None, None
        result_type = 'NO_MATCHING_C0061_NFC_PANIC_RECORD'
    return {
        'classification': result_type,
        'source_oops_zip_sha256': digest(oops_zip.read_bytes()),
        'source_module_zip_sha256': digest(module_zip.read_bytes()),
        'raw_oops_sha256': digest(raw),
        'record_size_bytes': CHUNK_BYTES,
        'record_headers_checked': len(records),
        'matching_panic_record_index_zero_based': idx,
        'matching_panic_record_sha256': digest(records[idx]) if idx is not None else None,
        'qgki_dep_count': len(qgki),
        'gki_dep_count': len(gki),
        'selected_panic_record': record,
        'original_boot_qgki_vs_gki': 'QGKI_SET_STRONGLY_SUPPORTED' if result_type.startswith('STRONG_QGKI') else 'UNKNOWN',
        'first_qgki_probe': 'UNKNOWN',
        'new_diagnostic_boot_effective_branch': 'UNKNOWN',
        'nfc_runtime_fix_verified': False,
        'flash_authorized': False,
        'cautions': [
            'Module-set correlation cannot attest exact OEM script branch or ELF pathname',
            'Original captured boot differs from new built-in NFC+module_blacklist experiment',
            'Earlier first-stage /lib/modules/5.4-gki attempts are independent of OEM vendor QGKI batch',
            'The audio/DSP init exec status 1 is independent of vendor_modprobe.sh initial probe',
            'The OEM ring buffer may contain old records; correlated evidence is within one validated record',
        ]
    }


def self_test() -> None:
    q={'nfc_i2c','alpha','beta','delta','epsilon','zeta','eta','theta','iota','kappa','lambda','mu'}
    g={'nfc_i2c','zeta'}
    markers=''.join(f'<6>[   12.100000] LISA0054_MODULE name={n} core=x\n' for n in sorted(q-{'nfc_i2c'}))
    linked=' '.join(sorted(q-{'nfc_i2c'}))+' nfc_i2c'
    good=(markers+f'<6>[   41.658342] Modules linked in: {linked}\n'
          '<6>[   41.724807] Comm: nqnfcinfo\n'
          '<6>[   41.724831] lr : nfc_dev_open+0x30/0xf0 [nfc_i2c]\n'
          '<0>[   41.797828] Kernel panic - not syncing: Fatal exception\n').encode()
    out=parse_record(good,q,g)
    assert out['route_inference'].startswith('STRONG_QGKI')
    assert out['active_modules_gki_only']==0 and out['panic_seconds']==41.797828
    mixed=parse_record(b'nfc_dev_open\nKernel panic - not syncing:\n',q,g)
    assert not mixed['nfc_panic_correlated_within_record']
    no_panic=parse_record(b'nqnfcinfo\nnfc_dev_open\n',q,g)
    assert not no_panic['nfc_panic_correlated_within_record']
    assert not parse_record(b'only other symbols',q,g)['nfc_panic_correlated_within_record']
    # An old ring snapshot's NFC stack and a later boot's panic must never mix.
    split=(b'<6>[   18.859866] Comm: nqnfcinfo; nfc_dev_open\n'
           b'<6>[   19.153544] marker\n'
           b'<6>[    0.000000] new boot\n'
           b'<0>[   41.797828] Kernel panic - not syncing: Fatal exception\n')
    assert not parse_record(split,q,g)['nfc_panic_correlated_within_record']
    print('C0061_OEM_OOPS_ROUTE_SELF_TEST=PASS')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--oops-zip',type=Path)
    ap.add_argument('--module-zip',type=Path)
    ap.add_argument('--json',type=Path)
    ap.add_argument('--self-test',action='store_true')
    a=ap.parse_args()
    if a.self_test:
        self_test()
        return
    if not a.oops_zip or not a.module_zip or not a.json:
        ap.error('--oops-zip, --module-zip, and --json required')
    result=run(a.oops_zip,a.module_zip)
    a.json.parent.mkdir(parents=True,exist_ok=True)
    a.json.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C0061_OEM_OOPS_ROUTE='+result['classification'])
    print('C0061_FIRST_PROBE=UNKNOWN')
    print('C0061_DEVICE_FIX=NOT_VERIFIED')

if __name__=='__main__':
    main()