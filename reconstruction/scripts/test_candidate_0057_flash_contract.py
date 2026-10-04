"""Negative and positive gate tests; no network or real device is needed."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from candidate_0057_flash_contract import PROP, PROP_CRC, assert_edge, checked_module


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.args = [
            {'module_layout': '0xba39cbb8', PROP: PROP_CRC}, {PROP},
            {'qti_battery_charger_main_k8'},
            {'__crc_' + PROP: ('A', int(PROP_CRC, 16)), PROP: ('T', 64),
             '__ksymtab_' + PROP: ('r', 0)},
            {'module_layout': '0xba39cbb8', 'power_debug_print_enabled': '0x621d7dcb'},
            {'module_layout': ('0xba39cbb8', 'vmlinux'),
             'power_debug_print_enabled': ('0x621d7dcb', 'vmlinux')},
        ]

    def test_valid_stock_edge(self):
        self.assertEqual(assert_edge(*self.args), {'flash': 1, 'battery': 2})

    def test_missing_dependency(self):
        self.args[2].clear()
        with self.assertRaisesRegex(RuntimeError, 'import/depend'): assert_edge(*self.args)

    def test_missing_import(self):
        self.args[1].clear()
        with self.assertRaisesRegex(RuntimeError, 'import/depend'): assert_edge(*self.args)

    def test_wrong_consumer_crc(self):
        self.args[0][PROP] = '0x00000000'
        with self.assertRaisesRegex(RuntimeError, 'import CRC'): assert_edge(*self.args)

    def test_wrong_provider_crc(self):
        self.args[3]['__crc_' + PROP] = ('A', 0)
        with self.assertRaisesRegex(RuntimeError, 'export CRC'): assert_edge(*self.args)

    def test_data_is_not_code(self):
        self.args[3][PROP] = ('D', 64)
        with self.assertRaisesRegex(RuntimeError, 'not code'): assert_edge(*self.args)

    def test_missing_export(self):
        del self.args[3]['__ksymtab_' + PROP]
        with self.assertRaisesRegex(RuntimeError, 'not exported'): assert_edge(*self.args)

    def test_duplicate_core_provider(self):
        self.args[5][PROP] = (PROP_CRC, 'vmlinux')
        with self.assertRaisesRegex(RuntimeError, 'duplicated'): assert_edge(*self.args)

    def test_wrong_core_crc(self):
        self.args[5]['module_layout'] = ('0x00000000', 'vmlinux')
        with self.assertRaisesRegex(RuntimeError, 'import mismatch'): assert_edge(*self.args)

    def test_missing_battery_dependency(self):
        del self.args[5]['power_debug_print_enabled']
        with self.assertRaisesRegex(RuntimeError, 'import mismatch'): assert_edge(*self.args)

    def test_hash_rejects_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'module.ko'
            path.write_bytes(b'incorrect module')
            with self.assertRaisesRegex(RuntimeError, 'SHA256'): checked_module(path, '0' * 64)


if __name__ == '__main__':
    unittest.main()
