#!/usr/bin/env python3
"""Prepare C0061 NFC built-in CONFIG_CMDLINE variant, never compile or flash.

This is a fail-closed, offline variant of the original successful C0061 NFC=y
.config from Action 38062935154. Every mutation is output-only and identified.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import tempfile

BASE_SHA = '80b3d3f814a2d6d8e44ff8b9e1f8eec25723d8c92c2a7726f8df81596f6e1795'
OLD = 'CONFIG_CMDLINE="ramoops_memreserve=4M"'
NEW = 'CONFIG_CMDLINE="ramoops_memreserve=4M module_blacklist=nfc_i2c"'
REQUIRED = [
    'CONFIG_CMDLINE_EXTEND=y',
    '# CONFIG_CMDLINE_FORCE is not set',
    'CONFIG_NFC_QTI_I2C=y',
    'CONFIG_MTD_OOPS=y',
    'CONFIG_MTD_BLOCK2MTD=y',
    'CONFIG_MODVERSIONS=y',
    'CONFIG_CFI_CLANG=y',
    'CONFIG_MODULES=y',
]

def sha_bytes(buf: bytes) -> str:
    return hashlib.sha256(buf).hexdigest()

def transform(src: bytes, *, enforce_sha: bool = True) -> tuple[bytes, list[str]]:
    if enforce_sha and sha_bytes(src) != BASE_SHA:
        raise ValueError('base .config SHA differs from Action 38062935154 exact build')
    text = src.decode('utf-8')
    if text.count(OLD) != 1:
        raise ValueError('expected exactly one unchanged baseline CONFIG_CMDLINE')
    for token in REQUIRED:
        if token not in text.splitlines():
            raise ValueError('missing original C0061 safety config: '+token)
    if re.search(r'(?m)^CONFIG_CMDLINE=',text).group(0) != 'CONFIG_CMDLINE=':
        raise ValueError('CONFIG_CMDLINE row unavailable')
    new = text.replace(OLD,NEW,1)
    before = text.splitlines(True)
    after = new.splitlines(True)
    diff = list(difflib.unified_diff(before, after, fromfile='compiled-nfc-builtin.config',tofile='candidate-embedded-blacklist.config'))
    if len([l for l in diff if l.startswith('-') and not l.startswith('---')]) != 1:
        raise ValueError('unexpected removed rows')
    if len([l for l in diff if l.startswith('+') and not l.startswith('+++')]) != 1:
        raise ValueError('unexpected added rows')
    return new.encode('utf-8'),diff

def write_out(src: Path, out: Path, manifest: Path, diff_path: Path):
    if len({str(p.resolve()) for p in (src,out,manifest,diff_path)}) != 4:
        raise ValueError('refusing to overwrite source or reuse output destinations')
    if any(p.exists() for p in (out,manifest,diff_path)):
        raise ValueError('refusing to overwrite existing output')
    if src.stat().st_size > 1024*1024:
        raise ValueError('config unexpectedly large')
    old=src.read_bytes();new,diff=transform(old)
    report={
      'kind':'UNCOMPILED_LOCAL_CONFIG_VARIANT_ONLY',
      'source_run':38062935154,
      'source_sha256':sha_bytes(old),
      'candidate_sha256':sha_bytes(new),
      'changed_config_keys':['CONFIG_CMDLINE'],
      'old_config_cmdline':'ramoops_memreserve=4M',
      'candidate_config_cmdline':'ramoops_memreserve=4M module_blacklist=nfc_i2c',
      'config_cmdline_extend_preserved':True,
      'boot_v3_header_cmdline_delivery_dependency_removed_if_rebuilt_from_candidate':True,
      'candidate_kernel_compiled':False,
      'candidate_boot_img_exists':False,
      'nfc_guard_compiled_in_the_SOURCE_build':True,
      'compiler_and_toolchain_reuse_required':True,
      'next_required_build_steps':['Recreate exact same C0061 direct-302 source+ABI oracle locally, not by editing frozen C0059', 'Install candidate .config BEFORE olddefconfig, then verify CMDLINE, EXTEND, NFC=y and security config retained', 'Select a distinct new release/localversion identity and complete single changed full kernel build', 'Verify Module.symvers/CRC/KMI/source/version/config and OEM Oops capability', 'Use stock-preserving fixed-region Boot repack, validate full avb and A/B rollback independently, keep NOT_FLASHABLE until complete'],
      'unverified_risks':['OEM first non-blocklisted QGKI probe unknown; blacklist may cause all-GKI fallback','New build does not bypass OEM signing, rollback, or full recovery requirements','New Android device runtime and NFC functionality untested'],
      'release_gate':'BLOCKED_NOT_FLASHABLE',
      'flash_authorized':False,
    }
    for path in (out,manifest,diff_path):path.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(new)
    diff_path.write_text(''.join(diff))
    manifest.write_text(json.dumps(report,indent=2)+'\n')
    print('C0061_SINGLE_LINE_CONFIG_DIFF=PASS')
    print('C0061_CONFIG_DRAFT_UNBUILT=YES')
    print('C0061_KERNEL_BUILT=NO')
    print('C0061_BOOT_PACKAGED=NO')
    print('C0061_FLASH_AUTHORIZED=false')

def self_test():
    tiny='\n'.join([OLD]+REQUIRED+['CONFIG_LOCALVERSION="-qgki-lisa-c0061-rf13410b-by-Tim0320"'])+'\n'
    patched,diff=transform(tiny.encode(),enforce_sha=False)
    assert NEW.encode() in patched and len(diff)>0
    for modified in (tiny.replace(OLD,'CONFIG_CMDLINE="garbage"'),
                     tiny.replace('CONFIG_NFC_QTI_I2C=y','CONFIG_NFC_QTI_I2C=m'),
                     tiny.replace('CONFIG_CMDLINE_EXTEND=y','CONFIG_CMDLINE_FORCE=y'),
                     tiny+OLD+'\n'):
        try:transform(modified.encode(),enforce_sha=False)
        except ValueError:pass
        else:raise ValueError('invalid synthetic input accepted')
    print('C0061_CONFIG_DRAFT_SYNTHETIC_SELF_TEST=PASS (1 positive, 4 negative)')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--manifest',type=Path)
    p.add_argument('--diff',type=Path)
    p.add_argument('--self-test',action='store_true')
    a=p.parse_args();self_test()
    if a.self_test:return
    if not all((a.source,a.output,a.manifest,a.diff)):
        raise SystemExit('required --source, --output, --manifest, --diff')
    write_out(a.source,a.output,a.manifest,a.diff)

if __name__=='__main__':main()