#!/usr/bin/env python3
"""Exercise the compiled ARM64 Image in an ephemeral, diskless QEMU guest.

A boot failure is inconclusive, not a BPF pass. The saved UNVERIFIED checkpoint
survives either outcome. This gate does not validate Qualcomm phone hardware.
"""
from pathlib import Path
import gzip
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def initramfs(binary):
    output = bytearray()
    entries = [('dev', stat.S_IFDIR | 0o755, b'', 0, 0),
               ('proc', stat.S_IFDIR | 0o755, b'', 0, 0),
               ('sys', stat.S_IFDIR | 0o755, b'', 0, 0),
               ('tmp', stat.S_IFDIR | 0o1777, b'', 0, 0),
               ('dev/console', stat.S_IFCHR | 0o600, b'', 5, 1),
               ('init', stat.S_IFREG | 0o755, binary, 0, 0),
               ('TRAILER!!!', 0, b'', 0, 0)]
    for ino, (name, mode, data, major, minor) in enumerate(entries, 1):
        encoded = name.encode() + b'\0'
        fields = [ino, mode, 0, 0, 1, 0, len(data), 0, 0, major, minor, len(encoded), 0]
        output.extend(b'070701' + ''.join(f'{x:08x}' for x in fields).encode())
        output.extend(encoded)
        output.extend(b'\0' * (-len(output) % 4))
        output.extend(data)
        output.extend(b'\0' * (-len(output) % 4))
    return gzip.compress(bytes(output), compresslevel=1, mtime=0)


def main():
    record = dict(kernel='actual Candidate0059 ARM64 Image',
                  device_hardware_tested=False, state='NOT_RUN')
    dest = ROOT / 'candidate-0059-bpf-qemu.json'
    try:
        cc = shutil.which('aarch64-linux-gnu-gcc')
        emulator = shutil.which('qemu-system-aarch64')
        if not cc or not emulator:
            raise RuntimeError('ARM64 static compiler or QEMU missing')
        source = ROOT / 'reconstruction/scripts/candidate_0059_ringbuf_probe.c'
        binary = ROOT / 'candidate-0059-ringbuf-probe-aarch64'
        subprocess.run([cc, '-static', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(source), '-o', str(binary)], check=True)
        raw = binary.read_bytes()
        if raw[:5] != b'\x7fELF\x02' or int.from_bytes(raw[18:20], 'little') != 183:
            raise RuntimeError('Probe is not an ARM64 ELF64 executable')
        image = ROOT / 'candidate-0059-Image'
        ramfs = ROOT / 'candidate-0059-bpf-probe-initramfs.gz'
        ramfs.write_bytes(initramfs(raw))
        record.update(image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                      probe_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      probe_elf_sha256=hashlib.sha256(raw).hexdigest())
        command = [emulator, '-machine', 'virt,gic-version=3', '-cpu', 'cortex-a57',
                   '-smp', '2', '-m', '1536', '-nographic', '-no-reboot',
                   '-kernel', str(image), '-initrd', str(ramfs), '-append',
                   'console=ttyAMA0 rdinit=/init loglevel=6 panic=5']
        log = ROOT / 'candidate-0059-bpf-qemu.log'
        record['command'] = command
        with log.open('wb') as stream:
            try:
                result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                        timeout=150, check=False)
                record['exit_code'] = result.returncode
            except subprocess.TimeoutExpired:
                record['timeout_seconds'] = 150
        text = log.read_text(errors='replace')
        if 'LISA_BPF59_TARGET_PROBE_FAIL' in text or 'BPF59_TEST FAIL ' in text:
            record['state'] = 'FAIL'
            raise RuntimeError('BPF target execution/verifier regression failed; inspect QEMU log')
        begin = 'LISA_BPF59_TARGET_PROBE_BEGIN' in text
        if 'LISA_BPF59_TARGET_PROBE_PASS' not in text:
            if begin:
                record['state'] = 'INCONCLUSIVE_EXECUTION'
                raise RuntimeError('BPF probe began but did not complete; inspect target log')
            record['state'] = 'INCONCLUSIVE_BOOT'
            record['note'] = ('Phone-specific Image did not reach init on generic QEMU virt; '
                              'this is not a BPF pass or BPF failure')
            print('LISA_CANDIDATE_0059_BPF_QEMU_GATE=INCONCLUSIVE_BOOT', flush=True)
            return
        if record.get('exit_code') != 0:
            record['state'] = 'FAIL_EXIT'
            raise RuntimeError('Probe marker present but QEMU did not shut down cleanly')
        record['state'] = 'PASS'
        print('LISA_CANDIDATE_0059_BPF_QEMU_GATE=PASS', flush=True)
    except Exception as error:
        record['error'] = str(error)
        raise
    finally:
        dest.write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    main()
