#!/usr/bin/env python3
"""Small-file checkpoint roundtrip/failure tests; no kernel build required."""
from pathlib import Path
import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import candidate_0057_artifacts as ck

SHA = '3d372a0e663fcf3fca0bc9c5389c26c1d52ff112'
RUN = '37181431324'

class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.src = self.base / 'source'; self.dst = self.base / 'restored'
        env = patch.dict(os.environ, {'GITHUB_ENV': str(self.base / 'isolated-test-env')})
        env.start(); self.addCleanup(env.stop)
        for root in (self.src, self.dst):
            for folder in ('scripts', 'overlays'):
                shutil.copytree(ck.ROOT / 'reconstruction' / folder, root / 'reconstruction' / folder,
                                ignore=shutil.ignore_patterns('__pycache__'))
            old = '.github/workflows/build-lisa-candidate-0053-arm64-fault-capture.yml'
            (root / old).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ck.ROOT / old, root / old)
            active = '.github/workflows/build-lisa-candidate-0057-ownership-identity.yml'
            shutil.copyfile(ck.ROOT / active, root / active)
        for name in ck.REQUIRED:
            p = self.src / name; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(('fixture:'+name+'\n').encode())
        self.arc = self.base / 'checkpoint.tar.gz'
        with patch.dict(os.environ, {'GITHUB_SHA':SHA, 'GITHUB_RUN_ID':RUN}):
            ck.save(self.src, self.arc)
    def restore(self, commit=SHA, run=RUN): ck.restore(self.dst, self.arc, commit, run)
    def test_roundtrip_no_compile(self):
        self.restore()
        for name in ck.REQUIRED: self.assertEqual((self.src/name).read_bytes(), (self.dst/name).read_bytes())
        record = json.loads((self.dst/ck.MANIFEST).read_text())
        self.assertEqual(record['state'], 'UNVERIFIED'); self.assertFalse(record['runtime_pass'])
    def test_wrong_source_commit(self):
        with self.assertRaisesRegex(RuntimeError, 'identity mismatch'): self.restore('1'*40)
    def test_wrong_source_run(self):
        with self.assertRaisesRegex(RuntimeError, 'identity mismatch'): self.restore(run='1')
    def test_missing_required_input_fails_before_archive(self):
        (self.src/'boot.img').unlink()
        with self.assertRaisesRegex(RuntimeError, 'Missing or unsafe'): ck.collect(self.src)
    def test_symlink_input_rejected(self):
        (self.src/'boot.img').unlink(); (self.src/'boot.img').symlink_to(self.base/'external')
        with self.assertRaisesRegex(RuntimeError, 'Missing or unsafe'): ck.collect(self.src)
    def test_credentials_not_collected(self):
        (self.src/'.env').write_text('SECRET=private'); (self.src/'.git').mkdir()
        (self.src/'.git/config').write_text('token')
        self.assertNotIn('.env', ck.collect(self.src)); self.assertNotIn('.git/config', ck.collect(self.src))
    def test_build_change_refuses_reuse(self):
        p = self.dst/'reconstruction/scripts/candidate_0057_identity.py'
        p.write_text(p.read_text().replace("'-by-Tim0320'", "'-by-other'"))
        with self.assertRaisesRegex(RuntimeError, 'full rebuild required'): self.restore()
    def test_verifier_only_change_keeps_build_fingerprint(self):
        p = self.dst/'reconstruction/scripts/candidate_0057_identity.py'
        p.write_text(p.read_text().replace("compiled_identity_gate='PASS'", "compiled_identity_gate='NEW_TEST'"))
        self.assertEqual(ck.recipe_fingerprint(self.src), ck.recipe_fingerprint(self.dst))
        self.restore()
    def test_tampered_bytes_rejected_before_writing(self):
        changed = self.base/'changed.tar.gz'
        with tarfile.open(self.arc, 'r:gz') as source, tarfile.open(changed, 'w:gz') as dest:
            for m in source.getmembers():
                data = source.extractfile(m).read()
                if m.name == 'boot.img': data = b'X'+data[1:]
                dest.addfile(m, io.BytesIO(data))
        self.arc = changed
        with self.assertRaisesRegex(RuntimeError, 'hash mismatch'): self.restore()
        self.assertFalse((self.dst/'boot.img').exists())
    def test_path_traversal_rejected(self):
        with tarfile.open(self.arc, 'w:gz') as dest:
            m = tarfile.TarInfo('../escape'); m.size = 1; dest.addfile(m, io.BytesIO(b'X'))
        with self.assertRaisesRegex(RuntimeError, 'Unsafe checkpoint'): self.restore()
    def test_symlink_archive_rejected(self):
        with tarfile.open(self.arc, 'w:gz') as dest:
            m = tarfile.TarInfo('boot.img'); m.type = tarfile.SYMTYPE; m.linkname='/tmp/escape'; dest.addfile(m)
        with self.assertRaisesRegex(RuntimeError, 'Unsafe checkpoint'): self.restore()
    def test_kernel_pin_change_refuses_reuse(self):
        p = self.dst/'.github/workflows/build-lisa-candidate-0057-ownership-identity.yml'
        p.write_text(p.read_text().replace('6e568aabc77a06fa787baec1d9e60e4b559874a3', '1'*40))
        with self.assertRaisesRegex(RuntimeError, 'full rebuild required'): self.restore()
    def test_verify_job_edit_does_not_rebuild_kernel(self):
        p = self.dst/'.github/workflows/build-lisa-candidate-0057-ownership-identity.yml'
        p.write_text(p.read_text().replace('Revalidate all gates without running make or packaging', 'Revalidate with corrected verifier'))
        self.assertEqual(ck.recipe_fingerprint(self.src), ck.recipe_fingerprint(self.dst))
        self.restore()
    def test_stale_verification_not_saved(self):
        (self.src/'candidate-0057-verification.json').write_text('{"result":"PASS"}')
        self.assertNotIn('candidate-0057-verification.json', ck.collect(self.src))

if __name__ == '__main__': unittest.main()
