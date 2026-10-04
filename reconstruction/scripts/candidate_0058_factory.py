#!/usr/bin/env python3
"""Generate the next version's wrappers from exact, reviewed Candidate0057 inputs.

Generated runtime functions, source pins and overlays are independently hashed by
checkpoint reuse. This factory never edits older candidates or kernel sources.
The expanded BPF patch and generated wrappers are exported in source artifacts.
"""
from pathlib import Path
import ast
import hashlib
import json
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PINS = {'candidate_0057_build.py': '9dcb290c68894fc2187421a8ff9974d5a0160877983799103daee23a7813d68d', 'candidate_0057_ownership_patch.py': '5882ee66b5780098af1263056929dd72ed5a33907a050e0fd820f7ff0f8387b7', 'candidate_0057_identity.py': 'f30df07fdef15c9e99d53b241dce557efa4cdaa97ba0e3c86f58ff2b9c643b62', 'candidate_0057_flash_contract.py': '6ff696819a4e5a6f21c88de3acd138822ac00ab938f25a886c824ecbbd0c63d2', 'candidate_0057_artifacts.py': '2ad830a2067a9063a56b3f7e1a0c0bd00bb3a5bdf485e1f52521b944f0b5490b', 'test_candidate_0057_identity.py': '4cd9e89cba4ec6b5ef963d105fa6e26bd027eda34421244911f5df88c9856fd5', 'test_candidate_0057_artifacts.py': 'b67cad5f9228535ff35c5701efb5af5956dbd53e3ea53530a0eef6d9fcea4a5d', 'test_candidate_0057_flash_contract.py': '3eddfbbec6244c12f69ef44040dcc5ad799d1691d7d6735ba776a13599cfe86d'}
EXPECTED = {'candidate_0058_build.py': '7d5c97008ff3ddb41fcfd23b0e73525b77c03ec17d58287e94135c5bcb8d5db1', 'candidate_0058_ownership_patch.py': '89fa87cd2cf4c5a832bc270fd111b093b30b5f8cf5c10949c38d398057ab5a7d', 'candidate_0058_identity.py': '23b3740ca5ff089d14718443ffac1b1958e9351bfe680f5ef6c7ad881509f371', 'candidate_0058_flash_contract.py': '38201d5d518b366451e0d169957d5420ebdb36d1c297ae52fe6bfe1004466b1d', 'candidate_0058_artifacts.py': 'f2d79e016ceb941e13c583523dc2224eb48a12fccf9f296dc59abd5a81ccabaa', 'test_candidate_0058_identity.py': 'aadc6b43ee794f7b3a47b56e28a292f962ef6658ec3d7555496746dfb93a8d51', 'test_candidate_0058_artifacts.py': 'f1573b5780e7d9753a544187f072e96b8f755e54098958b9a8952ee593c645c2', 'test_candidate_0058_flash_contract.py': 'a1d4229d3054ea3e83bcee19306a470f6065795f998d0b7f884c7d25f31dbb36'}


def main():
    script_dir = ROOT/'reconstruction/scripts'
    overlay = ROOT/'reconstruction/overlays'
    delta = overlay/'candidate_0058_recipe_delta.patch'
    text = delta.read_text()
    paths = set(re.findall(r'^\+\+\+ b/(.+)$', text, re.M))
    if not paths.issubset({'reconstruction/scripts/'+n for n in EXPECTED}):
        raise RuntimeError('Unexpected recipe patch target')
    blob = b''.join((overlay/f'candidate_0058_bpf_ringbuf.patch.gz.part{i:02d}').read_bytes() for i in range(4))
    if hashlib.sha256(blob).hexdigest() != 'd5a07d7a7e02291657d7c166dc311964fa3231d5c6c9f8dff40042251b9de0ee':
        raise RuntimeError('Transported BPF patch differs from reviewed source')
    with tempfile.TemporaryDirectory(prefix='lisa58-recipes-') as folder:
        root = Path(folder)
        dest = root/'reconstruction/scripts';dest.mkdir(parents=True)
        for name, digest in PINS.items():
            data=(script_dir/name).read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError('Candidate0057 recipe changed: '+name)
            (dest/name.replace('0057','0058')).write_text(data.decode().replace('0057','0058'))
        for flags in (['--check'], []):
            subprocess.run(['git','apply','--whitespace=error-all',*flags,str(delta)],cwd=root,check=True)
        for name, digest in EXPECTED.items():
            data=(dest/name).read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError('Generated wrapper mismatch: '+name)
            ast.parse(data.decode(),filename=name)
        for name in EXPECTED:
            shutil.copyfile(dest/name, script_dir/name)
    (overlay/'candidate_0058_bpf_ringbuf.patch.gz').write_bytes(blob)
    (ROOT/'candidate-0058-generated-recipes.json').write_text(json.dumps(EXPECTED,indent=2)+'\n')
    print('LISA_CANDIDATE_0058_RECIPE_GENERATION=PASS',flush=True)


if __name__=='__main__':main()
