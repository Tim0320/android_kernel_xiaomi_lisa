#!/usr/bin/env python3
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = ROOT / "reconstruction/scripts/candidate_0046_build.py"
KERNEL = ROOT / "kernel"
OUT = KERNEL / "out"

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

if not BASE.is_file():
    raise SystemExit("Candidate0046 base script missing")

env = os.environ.copy()
env["CONFIG_USE_COMMON_CAMERA"] = "y"

subprocess.run([sys.executable, str(BASE)], cwd=ROOT, env=env, check=True)

camera_obj = OUT / "techpack/camera/drivers/camera.o"
system_map = OUT / "System.map"
if not camera_obj.is_file() or camera_obj.stat().st_size == 0:
    raise SystemExit("Candidate0047 camera.o missing: common camera build did not activate")
if not system_map.is_file():
    raise SystemExit("Candidate0047 System.map missing")

sm = system_map.read_text(errors="replace")
for sym in ["cam_req_mgr_init", "cam_req_mgr_driver"]:
    if sym not in sm:
        raise SystemExit(f"Candidate0047 built-in camera symbol missing: {sym}")

src_img = ROOT / "candidate-0046-Image"
src_cfg = ROOT / "candidate-0046.config"
src_ik = ROOT / "candidate-0046.ikconfig"
for p in [src_img, src_cfg, src_ik, ROOT / "boot.img"]:
    if not p.is_file() or p.stat().st_size == 0:
        raise SystemExit(f"Candidate0047 required output missing: {p.name}")

dst_img = ROOT / "candidate-0047-Image"
dst_cfg = ROOT / "candidate-0047.config"
dst_ik = ROOT / "candidate-0047.ikconfig"
shutil.copy2(src_img, dst_img)
shutil.copy2(src_cfg, dst_cfg)
shutil.copy2(src_ik, dst_ik)

camera_info = (
    "baseline=Candidate0046 A642L GPU selector repair\n"
    "single_variable=CONFIG_USE_COMMON_CAMERA=y exported into Candidate0046 make environment\n"
    "source_mutation_relative_to_candidate0046=none\n"
    "reason=donor techpack/camera/Makefile wraps the entire camera tree in ifdef CONFIG_USE_COMMON_CAMERA\n"
    "candidate0046_config_fact=CONFIG_ARCH_LAHAINA=y CONFIG_ARCH_YUPIK=y CONFIG_QGKI=y but CONFIG_USE_COMMON_CAMERA absent\n"
    "runtime_evidence=CamX CSLInitializeHW failed to acquire requestManager and camera provider SIGABRT looped\n"
    f"camera_object_bytes={camera_obj.stat().st_size}\n"
    "cam_req_mgr_init_in_system_map=1\n"
    "cam_req_mgr_driver_in_system_map=1\n"
    "camera_linkage=built-in via donor CONFIG_SPECTRA_CAMERA=y\n"
    "CANDIDATE_0047_COMMON_CAMERA_GATE=PASS\n"
)
(ROOT / "candidate-0047-camera-build.txt").write_text(camera_info)

manifest = (
    "candidate=Lisa Candidate 0047 common-camera request-manager repair\n"
    "baseline=Candidate0046\n"
    f"candidate_0047_image_sha256={sha256(dst_img)}\n"
    f"candidate_0047_boot_sha256={sha256(ROOT / 'boot.img')}\n"
    "mutation=make-environment only: CONFIG_USE_COMMON_CAMERA=y\n"
    "kernel_source_mutation_relative_to_candidate0046=none\n"
    "retained=Candidate0046 A642L GPU selector + current IPA SHMBridge guard/diagnostics\n"
    "focus=restore built-in Qualcomm camera request manager so CamX can acquire requestManager\n"
    "LISA_CANDIDATE_0047_FINAL_GATE=PASS\n"
)
(ROOT / "candidate-0047-manifest.txt").write_text(manifest)
print(camera_info)
print(manifest)
