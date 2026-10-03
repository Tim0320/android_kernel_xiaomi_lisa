"""Scoped battery-provider addition; retain the pinned Candidate0055 repair."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import types

UFS55_SHA = 'f5d54b338f5318a4a80fef80ef0d5ecce960d751'
EXPECTED = {'power_debug_print_enabled': '0x621d7dcb',
            'mi_power_save_battery_cave': '0x746eee3e'}


def retained(root):
    path = root / 'reconstruction/scripts/candidate_0055_ufs_patch.py'
    data = path.read_bytes()
    sha = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if sha != UFS55_SHA:
        raise RuntimeError('Pinned Candidate0055 UFS implementation changed')
    mod = types.ModuleType('candidate0056_retained_ufs')
    mod.__file__ = str(path)
    exec(compile(data.decode().replace('0055', '0056'), str(path), 'exec'), mod.__dict__)
    return mod


def apply(root: Path, kernel: Path) -> None:
    source = root / 'reconstruction/overlays/lisa_power_compat.c'
    header = root / 'reconstruction/overlays/lisa_power_compat.h'
    cp = kernel / 'kernel/power/lisa_power_compat.c'
    hp = kernel / 'include/linux/lisa_power_compat.h'
    mp = kernel / 'kernel/power/Makefile'
    make = mp.read_text()
    if cp.exists() or hp.exists() or 'lisa_power_compat.o' in make:
        raise RuntimeError('Power provider was already installed; refusing double patch')
    if not source.is_file() or not header.is_file():
        raise RuntimeError('Power provider source/header missing')
    stock = (Path(os.environ['STOCK_ABI_ROOT']) / 'include/linux/power_debug.h').read_text()
    declarations = ('bool power_debug_print_enabled(void);',
                    'ssize_t mi_power_save_battery_cave(ssize_t capcity);')
    for declaration in declarations:
        if declaration not in stock:
            raise RuntimeError('Exact stock power declaration differs: ' + declaration)
    retained(root).apply(root, kernel)
    shutil.copyfile(source, cp)
    shutil.copyfile(header, hp)
    mp.write_text(make + '\n# Candidate0056 scoped battery ABI providers.\nobj-y += lisa_power_compat.o\n')
    (root / 'candidate-0056-power-source.txt').write_text(
        'evidence=023131 qti_battery_charger_main_k8 unresolved two power functions; stock headers confirm bool(void) and ssize_t(ssize_t)\n'
        'reference=LowTension/android_kernel_xiaomi_sm8475 39382bf mi-power capacity curve; not a full newer-platform power-driver transplant\n'
        'implementation=stateful debug flag; validated power-mode sysfs; unchanged percentage in normal modes; bounded vendor curve in save modes\n'
        'defensive_difference=out-of-contract percentages/errors are passed through rather than fabricated\n'
        'unchanged=charge limits/thermal/firmware/PAS/WLAN/CFI/UFS/procfs/display/audio/boot packaging\n'
        'scope=two missing providers, not complete OEM power debug hooks or a device pass\n'
        'CANDIDATE_0056_POWER_SOURCE_GATE=PASS\n')


def verify(root: Path) -> None:
    retained(root).verify(root)
    symbols = {}
    for line in (root / 'kernel/out/Module.symvers').read_text().splitlines():
        cols = line.split()
        if len(cols) >= 3:
            symbols[cols[1]] = (cols[0].lower(), cols[2])
    for name, crc in EXPECTED.items():
        if symbols.get(name) != (crc, 'vmlinux'):
            raise RuntimeError(f'Power provider ABI mismatch: {name}: {symbols.get(name)}; expected {crc} in vmlinux')
    image = (root / 'candidate-0056-Image').read_bytes()
    if b'LISA0056_POWER_COMPAT ready=1' not in image:
        raise RuntimeError('Power init marker not compiled into Image')
    sm = (root / 'kernel/out/System.map').read_text()
    for name in EXPECTED:
        if not re.search(r'\b[Tt] ' + name + r'(?:[.$][^\s]+)?(?:\n|$)', sm):
            raise RuntimeError('Provider is not linked as code: ' + name)
    obj = root / 'kernel/out/kernel/power/lisa_power_compat.o'
    if not obj.is_file() or not obj.stat().st_size:
        raise RuntimeError('Power provider object not compiled')
    cfg = (root / 'candidate-0056.ikconfig').read_text()
    for token in ('CONFIG_CFI_CLANG=y\n', '# CONFIG_CFI_PERMISSIVE is not set\n',
                  'CONFIG_MI_MEMORY_SYSFS=m\n', 'CONFIG_QCOM_QMI_HELPERS=y\n'):
        if token not in cfg:
            raise RuntimeError('Unrelated configuration changed: ' + token.strip())
    (root / 'candidate-0056-power-verified.txt').write_text(
        'power_provider_export_crc_matches=2/2\n'
        'power_provider_code_symbols=2/2\n'
        'power_provider_object_present=1\n'
        'stock_headers_checked=1\n'
        'device_test=pending\n'
        'LISA_CANDIDATE_0056_POWER_COMPILED_GATE=PASS\n')
    print('LISA_CANDIDATE_0056_POWER_COMPILED_GATE=PASS', flush=True)
