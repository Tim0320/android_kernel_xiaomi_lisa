"""Audited, privileged ring-buffer stage of the Linux5.10 BPF backport.

This is not whole-subsystem5.10 parity. Existing network/task/LSM structures,
capabilities, arm64 JIT, device drivers and filesystem code are not replaced.
"""
from pathlib import Path
import gzip
import hashlib
import json
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
META = 'reconstruction/overlays/candidate_0058_bpf_sources.json'
PATCH = 'reconstruction/overlays/candidate_0058_bpf_ringbuf.patch.gz'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def payload(root=ROOT):
    meta = json.loads((root / META).read_text())
    compressed = (root / PATCH).read_bytes()
    if digest(compressed) != meta['gzip_sha256']:
        raise RuntimeError('BPF patch compressed hash mismatch')
    raw = gzip.decompress(compressed)
    if digest(raw) != meta['patch_sha256']:
        raise RuntimeError('BPF patch source hash mismatch')
    paths = re.findall(r'^diff --git a/(\S+) b/', raw.decode(), re.M)
    if set(paths) != set(meta['files']) or len(paths) != len(set(paths)):
        raise RuntimeError('BPF patch inventory mismatch')
    for path in paths:
        if '..' in Path(path).parts or path.startswith('/'):
            raise RuntimeError('BPF patch path invalid')
        if not (path.startswith(('include/linux/bpf', 'include/uapi/linux/bpf',
                                 'kernel/bpf/', 'tools/testing/selftests/bpf/')) or
                path in ('kernel/trace/bpf_trace.c', 'net/core/filter.c',
                         'tools/include/uapi/linux/bpf.h')):
            raise RuntimeError('Out-of-scope BPF source change: ' + path)
    return raw, meta


def check_source(kernel, root=ROOT):
    _, meta = payload(root)
    for name, hashes in meta['files'].items():
        p = kernel / name
        if not p.is_file() or digest(p.read_bytes()) != hashes['after']:
            raise RuntimeError('BPF final-source hash differs: ' + name)
    return meta


def apply(root, kernel):
    raw, meta = payload(root)
    # Refuse every unexpected source before changing any file.
    for name, hashes in meta['files'].items():
        p = kernel / name
        if hashes['before'] is None:
            if p.exists():
                raise RuntimeError('BPF new source already exists: ' + name)
        elif not p.is_file() or digest(p.read_bytes()) != hashes['before']:
            raise RuntimeError('BPF pinned source differs: ' + name)
    path = root / 'candidate-0058-bpf-applied.patch'
    path.write_bytes(raw)
    subprocess.run(['git', 'apply', '--check', '--whitespace=error-all', str(path)],
                   cwd=kernel, check=True)
    subprocess.run(['git', 'apply', '--whitespace=error-all', str(path)],
                   cwd=kernel, check=True)
    check_source(kernel, root)
    (root / 'candidate-0058-bpf-source.json').write_text(json.dumps(meta, indent=2)+'\n')
    (root / 'candidate-0058-bpf-scope.txt').write_text(
        'stage=Linux5.10 ring-buffer API and verifier adaptation on Linux5.4.289\n'
        'map_type=27; helper_ids=130,131,132,133,134\n'
        'permission=CAP_SYS_ADMIN; no relaxation of existing program-load policy\n'
        'included=reserve/output/submit/discard/query,mmap,poll,reference/null/bounds checks\n'
        'included_hardening=helper-map-type match,zero-offset release,pending reservation bounds,irq_work_sync,spilling\n'
        'unsupported=full5.10BPF,iterators,trampolines,struct_ops,helper126-129,BTF-vmlinux,arraymmap\n'
        'ringbuf_freeze=EOPNOTSUPP; no readonly-consumer protocol fiction\n'
        'runtime_tests=must be reported separately; source and compile gates alone are insufficient\n'
        'not_fixed=Android16 continuity Java linkage,2G registration,transparent overlay corruption\n'
        'CANDIDATE_0058_BPF_SOURCE_GATE=PASS\n')


def install(base, root, kernel):
    original_sh = base.sh
    applied = False

    def sh(cmd, cwd=None, env=None):
        nonlocal applied
        if cmd and cmd[0] == 'make' and not applied:
            # All retained runtime source overlays have already been applied.
            apply(root, kernel)
            applied = True
        return original_sh(cmd, cwd=cwd, env=env)
    base.sh = sh


def verify(root):
    meta = check_source(root / 'kernel', root)
    cfg = (root / 'candidate-0058.ikconfig').read_text()
    for key in ('CONFIG_BPF_SYSCALL', 'CONFIG_BPF_JIT', 'CONFIG_CGROUP_BPF',
                'CONFIG_BPF_EVENTS', 'CONFIG_IRQ_WORK', 'CONFIG_CFI_CLANG',
                'CONFIG_MODVERSIONS'):
        if key+'=y\n' not in cfg:
            raise RuntimeError('BPF dependency/protection missing: '+key)
    symbols = {}
    for line in (root / 'kernel/out/System.map').read_text().splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = fields[1]
    for name in ('ringbuf_map_ops', 'bpf_ringbuf_output_proto', 'bpf_ringbuf_reserve_proto',
                 'bpf_ringbuf_submit_proto', 'bpf_ringbuf_discard_proto', 'bpf_ringbuf_query_proto'):
        if name not in symbols:
            raise RuntimeError('BPF linked object missing: '+name)
    for name in ('bpf_ringbuf_output', 'bpf_ringbuf_reserve', 'bpf_ringbuf_submit',
                 'bpf_ringbuf_discard', 'bpf_ringbuf_query'):
        if not any((n == name or n.startswith(name+'.')) and t in ('T','t')
                   for n,t in symbols.items()):
            raise RuntimeError('BPF helper has no linked code: '+name)
    for name in ('ringbuf.o','verifier.o'):
        p = root / 'kernel/out/kernel/bpf' / name
        if not p.is_file() or not p.stat().st_size:
            raise RuntimeError('BPF compiler object absent: '+name)
    result = dict(stage='ringbuf-v1', source_gate='PASS', linked_gate='PASS',
                  source_files=len(meta['files']), full_bpf510_parity=False,
                  target_device_tested=False, qemu_test='separate required workflow step')
    (root/'candidate-0058-bpf-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('LISA_CANDIDATE_0058_BPF_LINKED_GATE=PASS', flush=True)
