#!/usr/bin/env python3
"""Regression: Image contains linux_proc_banner before compiled linux_banner."""
import unittest
from unittest.mock import patch
from candidate_0057_identity import concrete_banner, identity

SHA = '3d372a0e663fcf3fca0bc9c5389c26c1d52ff112'
RELEASE = '5.4.289-qgki-lisa-c0057-r3d372a0-by-Tim0320'
BANNER = ('Linux version '+RELEASE+' (Tim0320@lisa-ci) (Android clang 11.0.2) '
          '#57 SMP PREEMPT Sun Oct 04 06:02:00 UTC 2026')

class IdentityTests(unittest.TestCase):
    def test_printf_template_before_banner(self):
        data = b'Linux version %s (%s)\x00other\x00'+BANNER.encode()+b'\n\x00'
        self.assertEqual(concrete_banner(data, RELEASE), BANNER)
    def test_template_only_is_not_identity(self):
        with self.assertRaises(RuntimeError): concrete_banner(b'Linux version %s (%s)\x00', RELEASE)
    def test_wrong_release(self):
        with self.assertRaises(RuntimeError): concrete_banner(BANNER.replace('3d372a0','fdf1a54').encode(), RELEASE)
    def test_wrong_author(self):
        with self.assertRaises(RuntimeError): concrete_banner(BANNER.replace('Tim0320@lisa-ci','stock@build').encode(), RELEASE)
    def test_wrong_build_number(self):
        with self.assertRaises(RuntimeError): concrete_banner(BANNER.replace('#57','#56').encode(), RELEASE)
    def test_multiple_conflicting_concrete_banners(self):
        with self.assertRaises(RuntimeError):
            concrete_banner(BANNER.encode()+b'\x00Linux version 5.4.289-stock (stock@build)\x00', RELEASE)
    def test_same_banner_duplicates_are_not_conflicts(self):
        self.assertEqual(concrete_banner((BANNER+'\x00'+BANNER).encode(), RELEASE), BANNER)
    def test_no_banner(self):
        with self.assertRaises(RuntimeError): concrete_banner(b'\x00Image\x00', RELEASE)
    def test_exact_commit_release(self):
        with patch.dict('os.environ', {'GITHUB_SHA': SHA}): self.assertEqual(identity(), RELEASE)
    def test_invalid_commits(self):
        for sha in ('', 'main', '3d372a0', 'g'*40, SHA+'\n'):
            with self.subTest(sha=sha), patch.dict('os.environ', {'GITHUB_SHA':sha}):
                with self.assertRaises(RuntimeError): identity()

if __name__ == '__main__': unittest.main()
