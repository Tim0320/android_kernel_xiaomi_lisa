"""Verify the pinned stock flash/battery edge, not the different donor stub.

The phone keeps its vendor modules. Rebuilt donor modules are ownership
probes, not replacements for the stock flash/battery binaries. Reference
OS2.0.3 bytes are not asserted equal to the user's OS2.0.8 modules.
"""
from pathlib import Path
import hashlib
import json
import shutil
import struct
import subprocess

REFERENCE_REPO = 'Jiovanni-dump/xiaomi_lisa_dump'
REFERENCE_COMMIT = '2dbe7b5569ed49cc2c6649a7b313d4a092755034'
REFERENCE_SHA256 = {
    'leds-qti-flash.ko': 'e935c3627c6e57515af45ed4e0582a07cd06f71f1d3c82e013c107343a0b89bc',
    'qti_battery_charger_main_k8.ko': '9f2f5f40484a765b5c81c63a83324ea8740eca1fc4c5ca9db321d1573a4609df',
}
PROP = 'qti_battery_charger_get_prop'
PROP_CRC = '0x47653d56'
HEADER_BLOB = '67660c72acec853ba6f616a49469c17fc1a5596d'


def checked_module(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError('Stock reference SHA256 differs: ' + path.name)
    if data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<HH', data, 16) != (1, 183):
        raise RuntimeError('Stock reference is not an ARM64 relocatable module: ' + path.name)


def reference_dir(root):
    return root / '.lisa-reference-0057'


def prepare(root):
    folder = reference_dir(root)
    folder.mkdir(exist_ok=True)
    for name, expected in REFERENCE_SHA256.items():
        path = folder / name
        if not path.is_file():
            url = f'https://raw.githubusercontent.com/{REFERENCE_REPO}/{REFERENCE_COMMIT}/vendor/lib/modules/{name}'
            temporary = path.with_suffix('.download')
            subprocess.run(['curl', '-fL', '--retry', '3', '--retry-all-errors',
                            '--connect-timeout', '15', '--max-time', '120',
                            url, '-o', str(temporary)], check=True)
            checked_module(temporary, expected)
            temporary.replace(path)
        checked_module(path, expected)
    print('LISA_CANDIDATE_0057_STOCK_FLASH_REFERENCE_PIN=PASS', flush=True)


def command(tool, *args):
    resolved = shutil.which(tool)
    if not resolved:
        raise RuntimeError('Required module inspection tool missing: ' + tool)
    return subprocess.check_output([resolved, *map(str, args)], text=True)


def versions(path):
    result = {}
    for line in command('modprobe', '--dump-modversions', path).splitlines():
        fields = line.split()
        if len(fields) != 2:
            raise RuntimeError('Malformed module version record: ' + line)
        crc, name = fields
        value = f'0x{int(crc, 16):08x}'
        if name in result:
            raise RuntimeError('Duplicate module version entry: ' + name)
        result[name] = value
    if not result or 'module_layout' not in result:
        raise RuntimeError('Reference module has no MODVERSIONS/module_layout data')
    return result


def assert_edge(flash_versions, flash_undefined, flash_depends, battery_symbols,
                battery_versions, providers):
    if 'qti_battery_charger_main_k8' not in flash_depends or PROP not in flash_undefined:
        raise RuntimeError('Stock flash does not import/depend on the pinned battery provider')
    if flash_versions.get(PROP) != PROP_CRC:
        raise RuntimeError('Stock flash property import CRC differs')
    if battery_symbols.get('__crc_' + PROP) != ('A', int(PROP_CRC, 16)):
        raise RuntimeError('Stock battery property export CRC differs')
    if battery_symbols.get(PROP, ('', 0))[0] not in ('T', 't'):
        raise RuntimeError('Stock battery property provider is not code')
    if '__ksymtab_' + PROP not in battery_symbols:
        raise RuntimeError('Stock battery property provider is not exported')
    if PROP in providers and providers[PROP][1] == 'vmlinux':
        raise RuntimeError('Stock battery property provider is duplicated in vmlinux')
    counts = {}
    for label, imported in (('flash', flash_versions), ('battery', battery_versions)):
        count = 0
        for name, expected in imported.items():
            if label == 'flash' and name == PROP:
                continue  # Explicitly verified against the stock module above.
            got = providers.get(name)
            if not got or got[0] != expected:
                raise RuntimeError(f'Stock {label} import mismatch: {name}: {got}; expected {expected}')
            count += 1
        counts[label] = count
    return counts


def verify(root):
    folder = reference_dir(root)
    for name, expected in REFERENCE_SHA256.items():
        checked_module(folder / name, expected)
    flash = folder / 'leds-qti-flash.ko'
    battery = folder / 'qti_battery_charger_main_k8.ko'
    kernel = root / 'kernel'
    header = (kernel / 'include/linux/soc/qcom/battery_charger.h').read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(header)).encode() + b'\0' + header).hexdigest()
    if blob != HEADER_BLOB:
        raise RuntimeError('Donor charger header changed; re-evaluate its conditional contract')
    cfg = (root / 'candidate-0057.ikconfig').read_text()
    if '# CONFIG_QTI_BATTERY_CHARGER is not set\n' not in cfg:
        raise RuntimeError('Generic donor charger unexpectedly enabled; not a verification-only change')
    nm_tool = 'aarch64-linux-gnu-nm' if shutil.which('aarch64-linux-gnu-nm') else 'nm'
    donor = kernel / 'out/drivers/leds/leds-qti-flash.ko'
    donor_undefined = {line.split()[-1] for line in command(nm_tool, '-u', donor).splitlines() if line.strip()}
    if PROP in donor_undefined:
        raise RuntimeError('Disabled generic donor charger unexpectedly remains an external import')
    flash_undefined = {line.split()[-1] for line in command(nm_tool, '-u', flash).splitlines() if line.strip()}
    dependencies = {item for item in command('modinfo', '-F', 'depends', flash).strip().split(',') if item}
    battery_symbols = {}
    for line in command(nm_tool, '--defined-only', battery).splitlines():
        fields = line.split()
        if len(fields) == 3:
            address, kind, name = fields
            battery_symbols[name] = (kind, int(address, 16))
    providers = {}
    for line in (kernel / 'out/Module.symvers').read_text().splitlines():
        fields = line.split()
        if len(fields) >= 3:
            providers[fields[1]] = (fields[0].lower(), fields[2])
    counts = assert_edge(versions(flash), flash_undefined, dependencies,
                         battery_symbols, versions(battery), providers)
    report = dict(reference_repo=REFERENCE_REPO, reference_commit=REFERENCE_COMMIT,
                  reference_sha256=REFERENCE_SHA256, reference_is_phone_readback=False,
                  donor_generic_charger_enabled=False, donor_flash_imports_property=False,
                  stock_flash_depends=sorted(dependencies), stock_property_crc=PROP_CRC,
                  stock_import_crc_matches=counts, phone_modules_replaced=False,
                  runtime_camera_flash_validated=False, gate='PASS')
    (root / 'candidate-0057-stock-flash-contract.json').write_text(json.dumps(report, indent=2) + '\n')
    print('LISA_CANDIDATE_0057_STOCK_FLASH_BATTERY_CONTRACT=PASS', flush=True)
