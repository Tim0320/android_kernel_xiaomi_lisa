#!/usr/bin/env python3
"""Source/ABI/integrity tests, not a substitute for the target verifier probe."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
import candidate_0059_bpf_port as port

class IntegrityTests(unittest.TestCase):
    def setUp(self): self.raw,self.meta=port.payload()
    def test_scope_and_upstream(self):
        self.assertIn('not full',self.meta['scope'])
        self.assertIn('457f44363a8894135c85b7a9afd2bd8196db24ab',self.meta['upstream'])
    def test_only_one_new_source(self):
        self.assertEqual([p for p,h in self.meta['files'].items() if h['before'] is None],['kernel/bpf/ringbuf.c'])
    def test_no_driver_or_security_replacement(self):
        self.assertFalse(any(p.startswith(('drivers/','security/','mm/','arch/')) for p in self.meta['files']))
    def test_no_shared_socket_structure_replacement(self):
        for p in ('include/net/sock.h','include/linux/skbuff.h','include/linux/netdevice.h','include/linux/sched.h'):
            self.assertNotIn(p,self.meta['files'])
    def test_required_hardening_in_patch(self):
        for s in (b'irq_work_sync(&rb->work)',b'new_prod_pos - pend_pos > rb->mask',
                  b'ringbuf release requires an acquired base pointer',b'type == PTR_TO_MEM_OR_NULL',
                  b'PTR_TO_MEM_OR_NULL:',b'reg->var_off.value >= BPF_MAX_VAR_SIZ'):
            self.assertIn(s,self.raw)
    def test_patch_carries_both_type_directions(self):
        self.assertIn(b'case BPF_MAP_TYPE_RINGBUF:',self.raw)
        self.assertIn(b'if (map->map_type != BPF_MAP_TYPE_RINGBUF)',self.raw)
    def test_no_global_enforcement_disabled(self):
        for s in (b'+CONFIG_CFI_PERMISSIVE=y',b'+CONFIG_SECURITY_SELINUX=n',b'+CONFIG_MODVERSIONS=n'):
            self.assertNotIn(s,self.raw)
    def test_corrupt_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in (port.META,port.PATCH):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(port.ROOT/name,p)
            p=root/port.PATCH;p.write_bytes(b'bad'+p.read_bytes())
            with self.assertRaisesRegex(RuntimeError,'compressed hash'):port.payload(root)


def source_roundtrip(source):
    raw,meta=port.payload()
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);kernel=root/'kernel';kernel.mkdir()
        for name in (port.META,port.PATCH):
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(port.ROOT/name,p)
        for name,h in meta['files'].items():
            if h['before']:
                p=kernel/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,p)
        subprocess.run(['git','init','-q'],cwd=kernel,check=True)
        before=(kernel/'include/linux/bpf.h').read_text()
        old_uapi=(kernel/'include/uapi/linux/bpf.h').read_text()
        port.apply(root,kernel)
        after=(kernel/'include/linux/bpf.h').read_text()
        for struct in ('bpf_map','bpf_map_ops','bpf_func_proto'):
            pattern=r'(?ms)^struct '+struct+r' \{.*?^\};'
            assert re.search(pattern,before).group()==re.search(pattern,after).group(),struct
        new=(kernel/'include/uapi/linux/bpf.h').read_text()
        def helpers(s):return re.findall(r'FN\((\w+)\)',s.split('#define __BPF_FUNC_MAPPER(FN)',1)[1].split('/* integer value',1)[0])
        oldnames,newnames=helpers(old_uapi),helpers(new)
        assert newnames[:len(oldnames)]==oldnames
        assert newnames[130:135]==['ringbuf_output','ringbuf_reserve','ringbuf_submit','ringbuf_discard','ringbuf_query']
        # A second application must fail before it changes an already patched tree.
        saved=(kernel/'kernel/bpf/verifier.c').read_bytes()
        try:port.apply(root,kernel)
        except RuntimeError:pass
        else:raise AssertionError('Repeated apply was not rejected')
        assert (kernel/'kernel/bpf/verifier.c').read_bytes()==saved
        print('BPF_SOURCE_ROUNDTRIP=PASS; shared struct ABI text unchanged; helper IDs stable')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path);args,rest=p.parse_known_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IntegrityTests))
    if not result.wasSuccessful():raise SystemExit(1)
    if args.source:source_roundtrip(args.source)
