#!/usr/bin/env python3
"""C0061: compare BUILT CONFIG_CMDLINE, authentic failed-boot Oops and Boot-v3 header.

Read-only, stdlib-only, bounded ZIP inputs. Never exports the full device cmdline
(which can contain serial numbers). This does not build, sign, flash or certify.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

BASELINE_ZIP_SHA = '74601294086e554adf5a1869eff2e08fd9c53133c1db76f85031483d09237a4c'
OOPS_ZIP_SHA = '1c27309687fe176744f98353fc77900837c7d95590c8b3e96f5db0483e898e43'
OOPS_RAW_SHA = '0e034b59946d562344dfb0295ce3cd0e6141f31bf4b685829ff2224f5b277e47'
DIAGNOSTIC_ZIP_SHA = 'c4181a81973f98c499482525fa08172ab896bd42f1b986db1a973ebee085f6c5'
BASELINE_BOOT_SHA = '038e35371c9705fd44908157ce456576100dfcb07f14ef60aa31e3b669c2eed6'
DIAGNOSTIC_BOOT_SHA = 'a4918b11c1f7ad2ae8df7444c587a3613afade2c91d800e494f06b331cb989c8'
OOPS_RECORD_BYTES = 2 * 1024 * 1024
BOOT_BYTES = 201326592
BOOT_HEADER_BYTES = 4096
BOOT_CMD_OFFSET, BOOT_CMD_LENGTH = 44, 1536
TARGET_PARAM = 'module_blacklist=nfc_i2c'
CMDLINE_KEY = 'ramoops_memreserve=4M'


def need(condition: bool, message: str):
    if not condition:
        raise ValueError('C0061_CMDLINE_FAIL_CLOSED: ' + message)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def zmember(z: ZipFile, name: str, max_bytes: int) -> bytes:
    info = z.getinfo(name)
    need(0 < info.file_size <= max_bytes, 'unsafe size for ' + name)
    return z.read(info)


def header_checks(header: bytes, expected_cmdline: str) -> dict:
    need(len(header) == BOOT_HEADER_BYTES, 'not a complete header page')
    need(header[:8] == b'ANDROID!', 'incorrect Android Boot magic')
    need(struct.unpack_from('<I', header, 20)[0] == 1580, 'unexpected v3 header size')
    need(struct.unpack_from('<I', header, 40)[0] == 3, 'not Android Boot v3')
    need(struct.unpack_from('<I', header, 8)[0] == 51436032, 'unexpected kernel region')
    raw = header[BOOT_CMD_OFFSET:BOOT_CMD_OFFSET+BOOT_CMD_LENGTH]
    cmd = raw.split(b'\0',1)[0].decode('ascii')
    need(cmd == expected_cmdline, 'unexpected Boot-v3 cmdline')
    need(not raw[len(cmd):].strip(b'\0'), 'unexpected remaining command line bytes')
    return {'android_header_version': 3, 'header_size': 1580,
            'header_cmdline': cmd or '<empty>', 'header_cmdline_propagated_to_kernel': 'UNVERIFIED'}


def digest_member_header(z: ZipFile, member: str, expected_sha: str, expected_cmdline: str) -> dict:
    info = z.getinfo(member)
    need(info.file_size == BOOT_BYTES, 'unexpected Boot size')
    h = hashlib.sha256()
    with z.open(member) as f:
        header = f.read(BOOT_HEADER_BYTES)
        h.update(header)
        for data in iter(lambda:f.read(1024*1024),b''):
            h.update(data)
    need(h.hexdigest() == expected_sha, 'Boot SHA mismatch')
    return header_checks(header, expected_cmdline)


def cfg_value(text: str, key: str) -> str:
    match = re.search(r'(?m)^' + re.escape(key) + r'=(.*)$',text)
    need(match is not None, key + ' missing')
    return match.group(1)


def verify_config(config_text: str, nfc: str, release: str) -> str:
    need(cfg_value(config_text, 'CONFIG_CMDLINE') == '"' + CMDLINE_KEY + '"', 'expected unmodified in-kernel ramoops parameter')
    for k in ('CONFIG_CMDLINE_EXTEND=y', '# CONFIG_CMDLINE_FORCE is not set',
              'CONFIG_MTD_OOPS=y', 'CONFIG_MTD_BLOCK2MTD=y',
              'CONFIG_MODVERSIONS=y', 'CONFIG_MODULES=y', 'CONFIG_CFI_CLANG=y'):
        need(k in config_text.splitlines(), 'missing config: '+k)
    need(cfg_value(config_text, 'CONFIG_NFC_QTI_I2C') == nfc, 'NFC variant mismatch')
    need(release in cfg_value(config_text, 'CONFIG_LOCALVERSION'), 'wrong kernel release')
    return CMDLINE_KEY


def check_oops(oops_zip: ZipFile) -> dict:
    n = next((s for s in oops_zip.namelist() if s.replace('\\','/').endswith('/lisa_oops_iter0001.bin')), None)
    need(n is not None, 'OEM Oops raw not found')
    data = zmember(oops_zip, n, 32*1024*1024)
    need(len(data) == 8*OOPS_RECORD_BYTES, 'expected genuine 16MiB OEM Oops partition')
    need(hashlib.sha256(data).hexdigest() == OOPS_RAW_SHA, 'OEM Oops raw SHA mismatch')
    record = data[OOPS_RECORD_BYTES:2*OOPS_RECORD_BYTES]
    need(record[4:8] == bytes.fromhex('005d005d'), 'mtdoops record1 marker not present')
    line = re.search(rb'(?m)^<\d+>\[\s*0\.000000\] Kernel command line: ([^\n\x00]+)',record)
    need(line is not None, 'no boot-relative zero Kernel command line in panic record')
    cmd = line.group(1).decode('ascii','replace').strip()
    need(cmd.startswith(CMDLINE_KEY+' '), 'in-kernel default not present as first real cmdline token')
    need(TARGET_PARAM not in cmd.split(), 'baseline already had NFC blacklist')
    panic_pos = record.find(b'Kernel panic - not syncing: Fatal exception')
    need(panic_pos > line.start(), 'NFC panic not after command line in same MTD record')
    need(b'nfc_dev_open' in record[line.start():panic_pos] and b'nqnfcinfo' in record[line.start():panic_pos], 'NFC first-fault signature incomplete')
    need(b'5.4.302-qgki-lisa-c0061-rfb3b3c2-by-Tim0320' in record[line.start():panic_pos], 'wrong original kernel identity')
    tokens = cmd.split()
    verified = {'ramoops_memreserve=4M','mtdoops.mtddev=0','mtdoops.record_size=2097152',
                'mtdoops.dump_oops=0','printk.always_kmsg_dump=1'}
    need(verified <= set(tokens), 'missing persistent OEM Oops command line tokens')
    return {
        'found_real_android_kernel_cmdline': True,
        'sanitized_kernel_cmdline_token_count': len(tokens),
        'sanitized_kernel_cmdline_char_count': len(cmd),
        'safe_relevant_runtime_tokens': sorted(verified),
        'baseline_config_cmdline_prefix_seen_first': True,
        'original_boot_blacklist_present': False,
        'same_oops_record_nfc_panic': True,
        'actual_future_boot_header_forwarding': 'UNKNOWN',
        'private_full_kernel_cmdline_exported': False,
    }


def inspect(baseline_zip: Path, oops_zip: Path, diag_zip: Path) -> dict:
    for p, sha in ((baseline_zip,BASELINE_ZIP_SHA),(oops_zip,OOPS_ZIP_SHA),(diag_zip,DIAGNOSTIC_ZIP_SHA)):
        need(digest(p) == sha, 'unexpected archive identity: ' + p.name)
    with ZipFile(baseline_zip) as base, ZipFile(oops_zip) as logs, ZipFile(diag_zip) as diag:
        for name,z in (('baseline',base),('oops',logs),('diagnostic',diag)):
            need(z.testzip() is None, name + ' ZIP CRC failed')
        bc = zmember(base,'candidate-0061-integrated-target.config',300000).decode()
        dc = zmember(diag,'builtin.config',300000).decode()
        verify_config(bc,'m','-c0061-rfb3b3c2-by-Tim0320')
        verify_config(dc,'y','-c0061-rf13410b-by-Tim0320')
        old_boot = digest_member_header(base,'boot.img',BASELINE_BOOT_SHA,'')
        new_boot = digest_member_header(diag,'C0061_NFC_BUILTIN_BLACKLIST_NOT_FLASHABLE_boot.img',DIAGNOSTIC_BOOT_SHA,TARGET_PARAM)
        oops = check_oops(logs)
    return {
        'type':'AUTHENTIC_ORIGINAL_BOOT_KERNEL_CONFIG_CMDLINE_VS_DIAGNOSTIC_HEADER',
        'source_zip_sha256':{'original_build':BASELINE_ZIP_SHA,'original_oops':OOPS_ZIP_SHA,'diagnostic':DIAGNOSTIC_ZIP_SHA},
        'original_boot':old_boot, 'diagnostic_boot':new_boot,
        'baseline_config':{'CONFIG_CMDLINE':CMDLINE_KEY,'CONFIG_CMDLINE_EXTEND':True,'CONFIG_NFC_QTI_I2C':'m'},
        'diagnostic_config':{'CONFIG_CMDLINE':CMDLINE_KEY,'CONFIG_CMDLINE_EXTEND':True,'CONFIG_NFC_QTI_I2C':'y'},
        'recorded_original_runtime':oops,
        'possible_future_robust_config_cmdline':CMDLINE_KEY+' '+TARGET_PARAM,
        'future_build_required_for_config_cmdline_change':True,
        'original_kernel_kconfig_param_delivery':'STRONGLY_CONFIRMED_REAL_ANDROID_BOOT',
        'new_header_only_param_delivery':'UNKNOWN_NOT_PROVEN_BY_ORIGINAL_BOOT',
        'oem_first_modprobe_probe':'UNKNOWN',
        'new_boot_fixes_nfc_panic':'UNVERIFIED',
        'device_test_completed':False,
        'flash_authorized':False,
        'release':'BLOCKED_NOT_FLASHABLE',
    }


def self_test():
    header = bytearray(BOOT_HEADER_BYTES)
    header[:8] = b'ANDROID!'
    struct.pack_into('<I',header,8,51436032)
    struct.pack_into('<I',header,20,1580)
    struct.pack_into('<I',header,40,3)
    need(header_checks(bytes(header),'')['android_header_version']==3, 'synthetic good header')
    header[44:44+len(TARGET_PARAM)]=TARGET_PARAM.encode()
    need(header_checks(bytes(header),TARGET_PARAM)['header_cmdline']==TARGET_PARAM, 'synthetic cmdline')
    for off in (0,20,40):
        b=header[:]
        b[off]=0 if b[off] else 255
        try: header_checks(bytes(b),TARGET_PARAM)
        except (ValueError, UnicodeError):pass
        else:raise ValueError('synthetic invalid header accepted')
    c='\n'.join(['CONFIG_CMDLINE="ramoops_memreserve=4M"','CONFIG_CMDLINE_EXTEND=y',
        '# CONFIG_CMDLINE_FORCE is not set','CONFIG_MTD_OOPS=y','CONFIG_MTD_BLOCK2MTD=y',
        'CONFIG_MODVERSIONS=y','CONFIG_MODULES=y','CONFIG_CFI_CLANG=y',
        'CONFIG_NFC_QTI_I2C=y','CONFIG_LOCALVERSION="-qgki-lisa-c0061-rf13410b-by-Tim0320"'])
    verify_config(c,'y','-c0061-rf13410b-by-Tim0320')
    for bad in (c.replace('CONFIG_CMDLINE_EXTEND=y','CONFIG_CMDLINE_FORCE=y'),
                c.replace('CONFIG_NFC_QTI_I2C=y','CONFIG_NFC_QTI_I2C=m')):
        try: verify_config(bad,'y','-c0061-rf13410b-by-Tim0320')
        except ValueError:pass
        else:raise ValueError('synthetic invalid config accepted')
    print('C0061_CMDLINE_SYNTHETIC_SELF_TEST=PASS (2 header positive, 3 header negative, 1 config positive, 2 config negative)')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--baseline-zip',type=Path)
    ap.add_argument('--oops-zip',type=Path)
    ap.add_argument('--diagnostic-zip',type=Path)
    ap.add_argument('--json',type=Path)
    ap.add_argument('--self-test',action='store_true')
    a=ap.parse_args()
    self_test()
    if a.self_test:return
    need(all((a.baseline_zip,a.oops_zip,a.diagnostic_zip,a.json)), 'required archive arguments missing')
    report=inspect(a.baseline_zip,a.oops_zip,a.diagnostic_zip)
    a.json.parent.mkdir(parents=True,exist_ok=True)
    a.json.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print('C0061_AUTHENTIC_CMDLINE_PROVENANCE=PASS')
    print('C0061_ORIGINAL_KCONFIG_CMDLINE_EFFECTIVE=YES')
    print('C0061_NEW_BOOT_V3_HEADER_CMDLINE_EFFECTIVE=UNKNOWN')
    print('C0061_FLASH_AUTHORIZED=false')

if __name__=='__main__':main()