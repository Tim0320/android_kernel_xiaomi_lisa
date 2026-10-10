#!/usr/bin/env python3
"""Evidence-only C0061 same-run XHCI export CRC / config drift audit.

This proves which compiled vmlinux exports changed relative to the rebuilt
C0059 control; it cannot infer which private OEM vendor .ko files import them,
nor Android first-fault, module load success, or device boot PASS.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

EXPECTED_CHANGED = {
    'xhci_dbg_trace', 'xhci_ext_cap_init', 'xhci_gen_setup',
    'xhci_resume', 'xhci_suspend',
}
XHCI_CONFIG = {
    'CONFIG_USB_XHCI_HCD', 'CONFIG_USB_XHCI_PCI',
    'CONFIG_USB_XHCI_PLATFORM', 'CONFIG_USB_DWC3',
    'CONFIG_USB_DWC3_MSM', 'CONFIG_MODVERSIONS',
}


def parse_symvers(path: Path) -> dict[str, tuple[str, str, str]]:
    exports: dict[str, tuple[str, str, str]] = {}
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 4 or not parts[0].startswith('0x'):
            raise ValueError(f'Invalid Module.symvers record line {i}: {path}')
        name, info = parts[1], (parts[0].lower(), parts[2], parts[3])
        if name in exports and exports[name] != info:
            raise ValueError(f'Conflicting export {name}: {path}')
        exports[name] = info
    if not exports:
        raise ValueError(f'Empty Module.symvers: {path}')
    return exports


def parse_config(path: Path) -> dict[str, str]:
    config: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            key, val = line.split('=', 1)
            config[key] = val
        elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
            config[line[2:].split(' ', 1)[0]] = 'n'
    if not config:
        raise ValueError(f'Empty kernel config: {path}')
    return config


def analyze(control: Path, target: Path, control_cfg: Path,
            target_cfg: Path) -> dict:
    old, new = parse_symvers(control), parse_symvers(target)
    removed = sorted(set(old) - set(new))
    added = sorted(set(new) - set(old))
    changed = sorted(name for name in old.keys() & new.keys()
                     if old[name][0] != new[name][0])
    ownership_changes = sorted(name for name in old.keys() & new.keys()
                               if old[name][1:] != new[name][1:])
    cfg_old, cfg_new = parse_config(control_cfg), parse_config(target_cfg)
    config_drift = {key: {'control': cfg_old.get(key), 'target': cfg_new.get(key)}
                    for key in sorted(cfg_old.keys() | cfg_new.keys())
                    if cfg_old.get(key) != cfg_new.get(key)}
    xhci_records = {
        name: {
            'control_crc': old[name][0], 'target_crc': new[name][0],
            'control_provider': old[name][1],
            'target_provider': new[name][1],
            'target_export_type': new[name][2],
        } for name in sorted(EXPECTED_CHANGED) if name in old and name in new
    }
    expected_config_delta = {'CONFIG_LOCALVERSION', 'CONFIG_SURFACE_PLATFORMS'}
    failures = []
    if removed:
        failures.append('Removed ABI symbols exist')
    if set(changed) != EXPECTED_CHANGED:
        failures.append(f'Changed exports drift: {changed}')
    if len(added) != 11:
        failures.append(f'Added ABI symbols drift: {len(added)}')
    if ownership_changes:
        failures.append(f'Export provider/type drift: {ownership_changes}')
    if set(config_drift) - expected_config_delta:
        failures.append(f'Unexpected build config drift: {sorted(set(config_drift) - expected_config_delta)}')
    for name, row in xhci_records.items():
        if row['control_provider'] != 'vmlinux' or row['target_provider'] != 'vmlinux':
            failures.append(f'XHCI export provider not vmlinux: {name}')
        if row['target_export_type'] != 'EXPORT_SYMBOL_GPL':
            failures.append(f'XHCI export type changed: {name}')
    for name in sorted(XHCI_CONFIG):
        if cfg_old.get(name) != 'y' or cfg_new.get(name) != 'y':
            failures.append(f'Expected built-in feature not y both builds: {name}')
    return {
        'result': 'PASS' if not failures else 'FAIL',
        'scope': 'SAME_RUN_C0059_VS_C0061_COMPILED_ABI_ONLY',
        'control_export_count': len(old),
        'target_export_count': len(new),
        'removed_export_count': len(removed),
        'added_export_count': len(added),
        'changed_crc_export_count': len(changed),
        'changed_crc_symbols': changed,
        'xhci_crc_records': xhci_records,
        'xhci_builtin_config': {key: {'control': cfg_old.get(key), 'target': cfg_new.get(key)}
                                for key in sorted(XHCI_CONFIG)},
        'config_drift': config_drift,
        'source_module_consumer_scan': 'NOT_AVAILABLE_IN_ARCHIVED_FULL_BUILD_ARTIFACT',
        'stock_vendor_xhci_importers': 'UNVERIFIED_NO_PRIVATE_VENDOR_ELFS_IN_CI',
        'android_vendor_module_directory_selected': 'UNVERIFIED',
        'android_first_fault': 'UNVERIFIED',
        'device_boot_pass': False,
        'failures': failures,
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        a, b = p/'old', p/'new'
        a.write_text('0x00000001\tfoo\tvmlinux\tEXPORT_SYMBOL_GPL\n')
        b.write_text('0x00000002\tfoo\tvmlinux\tEXPORT_SYMBOL_GPL\n')
        assert parse_symvers(a)['foo'][0] == '0x00000001'
        assert parse_symvers(b)['foo'][0] == '0x00000002'
        a.write_text(a.read_text() + '0x00000005\tfoo\tother\tEXPORT_SYMBOL\n')
        try:
            parse_symvers(a)
        except ValueError as exc:
            assert 'Conflicting export' in str(exc)
        else:
            raise AssertionError('Conflicting provider not detected')
        c = p/'config'
        c.write_text('CONFIG_USB_XHCI_HCD=y\n# CONFIG_MODULE_SIG is not set\n')
        assert parse_config(c)['CONFIG_MODULE_SIG'] == 'n'
        assert parse_config(c)['CONFIG_USB_XHCI_HCD'] == 'y'
    print('C0061_XHCI_ABI_AUDIT_SELF_TEST=PASS')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--control-symvers', type=Path)
    ap.add_argument('--target-symvers', type=Path)
    ap.add_argument('--control-config', type=Path)
    ap.add_argument('--target-config', type=Path)
    ap.add_argument('--json', type=Path)
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not all((args.control_symvers, args.target_symvers,
                args.control_config, args.target_config, args.json)):
        ap.error('control/target symvers/config and --json all required')
    result = analyze(args.control_symvers, args.target_symvers,
                     args.control_config, args.target_config)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print('C0061_XHCI_ABI_EXPOSURE_GATE=' + result['result'])
    print('C0061_XHCI_CHANGED_CRC_EXPORTS=' + str(result['changed_crc_export_count']))
    print('C0061_XHCI_EXPORT_PROVIDER=VMLINUX')
    print('ANDROID_DEVICE_BOOT_PASS=UNVERIFIED')
    for failure in result['failures']:
        print('C0061_XHCI_ABI_FAILURE=' + failure)
    return 0 if result['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
