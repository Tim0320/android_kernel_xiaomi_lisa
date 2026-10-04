"""Truthful Lisa UTS identity without changing module verification policy."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import re


def identity():
    sha = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise RuntimeError('GITHUB_SHA must identify the exact build package')
    return '5.4.289-qgki-lisa-c0057-r' + sha[:7] + '-by-Tim0320'


def set_config(text, key, value):
    pattern = r'(?m)^(?:' + re.escape(key) + r'=.*|# ' + re.escape(key) + r' is not set)$'
    replacement = '# ' + key + ' is not set' if value is None else key + '=' + value
    out, count = re.subn(pattern, replacement, text)
    if count != 1:
        raise RuntimeError(f'Identity config {key}: expected one entry, got {count}')
    return out


def check_loader(text):
    # Assert the existing MODVERSIONS rule, do not modify it. Kernel release
    # differences are ignored only for modules that actually contain CRCs.
    pattern = (r'static (?:inline )?int same_magic\([^{}]+\)\s*\{\s*'
               r'if \(has_crcs\) \{\s*amagic \+= strcspn\(amagic, " "\);\s*'
               r'bmagic \+= strcspn\(bmagic, " "\);\s*\}\s*'
               r'return strcmp\(amagic, bmagic\) == 0;\s*\}')
    if not re.search(pattern, text):
        raise RuntimeError('Pinned MODVERSIONS same_magic contract changed')
    if 'check_modstruct_version' not in text or 'check_version' not in text:
        raise RuntimeError('Module version checks missing')


def install(base, root: Path, kernel: Path):
    release = identity()
    base.TARGET_RELEASE = release.encode('ascii')
    original_sh = base.sh
    build_time = datetime.now(timezone.utc).strftime('%a %b %d %H:%M:%S UTC %Y')
    loader_hash = None
    configured = False

    def sh(cmd, cwd=None, env=None):
        nonlocal configured, loader_hash
        if cmd and cmd[0] == 'make':
            if not configured:
                path = kernel / 'out/.config'
                cfg = path.read_text()
                if 'CONFIG_MODVERSIONS=y\n' not in cfg:
                    raise RuntimeError('Branding requires the preserved MODVERSIONS contract')
                cfg = set_config(cfg, 'CONFIG_LOCALVERSION', '"' + release[len('5.4.289'):] + '"')
                cfg = set_config(cfg, 'CONFIG_LOCALVERSION_AUTO', None)
                # Refuse extra release fragments instead of silently hiding them.
                for folder in (kernel, kernel / 'out'):
                    for frag in folder.glob('localversion*'):
                        if frag.is_file() and frag.read_text().strip():
                            raise RuntimeError(f'Unexpected release fragment: {frag}')
                module = kernel / 'kernel/module.c'
                check_loader(module.read_text())
                loader_hash = hashlib.sha256(module.read_bytes()).hexdigest()
                path.write_text(cfg)
                configured = True
            actual = dict(os.environ if env is None else env)
            actual.update(LOCALVERSION='', KBUILD_BUILD_USER='Tim0320',
                          KBUILD_BUILD_HOST='lisa-ci', KBUILD_BUILD_VERSION='57',
                          KBUILD_BUILD_TIMESTAMP=build_time)
            result = original_sh(cmd, cwd=cwd, env=actual)
            if hashlib.sha256((kernel / 'kernel/module.c').read_bytes()).hexdigest() != loader_hash:
                raise RuntimeError('Module loader changed during branding/build')
            if 'Image' in cmd:
                uts = (kernel / 'out/include/generated/utsrelease.h').read_text()
                if f'#define UTS_RELEASE "{release}"' not in uts:
                    raise RuntimeError(f'Unexpected compiled UTS release: {uts}')
                data = {'release': release, 'package_commit': os.environ['GITHUB_SHA'],
                        'build_user': 'Tim0320', 'build_host': 'lisa-ci',
                        'build_version': 57, 'build_utc': build_time,
                        'linux_base': '5.4.289', 'module_loader_unchanged_sha256': loader_hash,
                        'stock_module_crcs_required': True, 'runtime_tested': False}
                (root / 'candidate-0057-identity.json').write_text(json.dumps(data, indent=2) + '\n')
            return result
        return original_sh(cmd, cwd=cwd, env=env)
    base.sh = sh


def verify(root: Path):
    release = identity()
    image = (root / 'candidate-0057-Image').read_bytes()
    banner = re.search(rb'Linux version [^\x00\n]+', image)
    if not banner:
        raise RuntimeError('Final Image has no Linux banner')
    text = banner.group().decode('ascii', 'replace')
    if not text.startswith('Linux version ' + release + ' ') or '(Tim0320@lisa-ci)' not in text:
        raise RuntimeError('Final Image branding differs from requested identity: ' + text)
    if '#57 SMP PREEMPT ' not in text or 'pangu-build-component-vendor' in text or 'g5987d69e25da' in text:
        raise RuntimeError('Old stock build identity survived in Linux banner')
    for name in ('candidate-0057.config', 'candidate-0057.ikconfig'):
        cfg = (root / name).read_text()
        for token in ('CONFIG_MODVERSIONS=y\n', 'CONFIG_CFI_CLANG=y\n',
                      '# CONFIG_CFI_PERMISSIVE is not set\n',
                      'CONFIG_LOCALVERSION="' + release[len('5.4.289'):] + '"\n',
                      '# CONFIG_LOCALVERSION_AUTO is not set\n'):
            if token not in cfg:
                raise RuntimeError(f'{name}: missing preserved identity/protection: {token}')
    result = json.loads((root / 'candidate-0057-identity.json').read_text())
    result.update(linux_banner=text, compiled_identity_gate='PASS')
    (root / 'candidate-0057-identity.json').write_text(json.dumps(result, indent=2) + '\n')
    print('LISA_CANDIDATE_0057_IDENTITY_GATE=PASS', flush=True)
