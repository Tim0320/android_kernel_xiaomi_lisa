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
os.environ["CONFIG_USE_COMMON_CAMERA"] = "y"

# Import Candidate0046 without executing its main() so Candidate0047 can apply
# the Lisa-specific camera flash selector before the common camera tree builds.
import importlib.util
spec = importlib.util.spec_from_file_location("candidate0046_base", BASE)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

def promote_lisa_qti_flash_builtin():
    cfg_path = ROOT / "candidate-0018.ikconfig"
    if not cfg_path.is_file() or cfg_path.stat().st_size == 0:
        raise SystemExit("Candidate0047 preserved Candidate0018 IKCONFIG missing")

    original = cfg_path.read_bytes()
    cfg = original.decode("utf-8", "replace")

    for dep in ["CONFIG_LEDS_CLASS_FLASH=y\n", "CONFIG_MFD_SPMI_PMIC=y\n"]:
        if dep not in cfg:
            raise SystemExit(f"Candidate0047 QTI flash built-in dependency missing: {dep.strip()}")

    if "CONFIG_LEDS_QTI_FLASH=m\n" in cfg:
        stock_state = "m"
        cfg = cfg.replace("CONFIG_LEDS_QTI_FLASH=m\n", "CONFIG_LEDS_QTI_FLASH=y\n", 1)
    elif "CONFIG_LEDS_QTI_FLASH=y\n" in cfg:
        stock_state = "y"
    else:
        raise SystemExit("Candidate0047 CONFIG_LEDS_QTI_FLASH is neither m nor y in preserved config")

    cfg_path.write_text(cfg)
    (ROOT / "candidate-0047-flash-linkage.txt").write_text(
        f"stock_CONFIG_LEDS_QTI_FLASH={stock_state}\n"
        "effective_CONFIG_LEDS_QTI_FLASH=y\n"
        "camera_linkage=built-in\n"
        "reason=IS_REACHABLE(CONFIG_LEDS_QTI_FLASH) is false for a built-in camera caller when QTI flash is modular; "
        "cam_flash_core also compiles QTI APIs under IS_ENABLED, so the provider must be built-in for a valid direct dependency\n"
        "original_candidate0018_restored_after_build=1\n"
        "CANDIDATE_0047_QTI_FLASH_LINKAGE_GATE=PASS\n"
    )
    return original

def patch_lisa_camera_flash_selector():
    dev_h = KERNEL / "techpack/camera/drivers/cam_sensor_module/cam_flash/cam_flash_dev.h"
    core_c = KERNEL / "techpack/camera/drivers/cam_sensor_module/cam_flash/cam_flash_core.c"
    pmic_dts = KERNEL / "arch/arm64/boot/dts/vendor/qcom/pm8350c.dtsi"
    qti_led = KERNEL / "drivers/leds/leds-qti-flash.c"

    dts = pmic_dts.read_text()
    led = qti_led.read_text()
    if 'compatible = "qcom,pm8350c-flash-led";' not in dts:
        raise SystemExit("Candidate0047 PM8350C QTI flash DTS identity missing")
    if '.compatible = "qcom,pm8350c-flash-led"' not in led:
        raise SystemExit("Candidate0047 QTI flash driver PM8350C match missing")

    h = dev_h.read_text()
    old_h = """#if IS_REACHABLE(CONFIG_LEDS_QPNP_FLASH_V2)
#include <linux/leds-qpnp-flash.h>
#elif IS_REACHABLE(CONFIG_LEDS_QTI_FLASH)
#include <linux/leds-qti-flash.h>
#endif
"""
    new_h = """/* Lisa/PM8350C is handled by leds-qti-flash.  The stock QGKI config can
 * expose both QTI and legacy QPNP flash symbols, so select the actual
 * PM8350C provider first instead of the generic legacy provider.
 */
#if IS_REACHABLE(CONFIG_LEDS_QTI_FLASH)
#include <linux/leds-qti-flash.h>
#elif IS_REACHABLE(CONFIG_LEDS_QPNP_FLASH_V2)
#include <linux/leds-qpnp-flash.h>
#endif
"""
    if h.count(old_h) != 1:
        raise SystemExit(f"Candidate0047 flash header selector anchor count={h.count(old_h)}")
    dev_h.write_text(h.replace(old_h, new_h, 1))

    c = core_c.read_text()
    old_c = """#if IS_REACHABLE(CONFIG_LEDS_QPNP_FLASH_V2)
		rc = qpnp_flash_led_prepare(trigger, options, max_current);
#elif IS_REACHABLE(CONFIG_LEDS_QTI_FLASH)
		rc = qti_flash_led_prepare(trigger, options, max_current);
#endif
"""
    new_c = """#if IS_REACHABLE(CONFIG_LEDS_QTI_FLASH)
		rc = qti_flash_led_prepare(trigger, options, max_current);
#elif IS_REACHABLE(CONFIG_LEDS_QPNP_FLASH_V2)
		rc = qpnp_flash_led_prepare(trigger, options, max_current);
#endif
"""
    if c.count(old_c) != 1:
        raise SystemExit(f"Candidate0047 flash prepare selector anchor count={c.count(old_c)}")
    core_c.write_text(c.replace(old_c, new_c, 1))

    (ROOT / "candidate-0047-camera-selector.txt").write_text(
        "device=Lisa SM7325/Yupik\n"
        "pmic_flash_compatible=qcom,pm8350c-flash-led\n"
        "provider=drivers/leds/leds-qti-flash.c\n"
        "legacy_qpnp_provider_matches=pm6150l,pmi632\n"
        "mutation=prefer CONFIG_LEDS_QTI_FLASH over CONFIG_LEDS_QPNP_FLASH_V2 in camera flash header/prepare selectors\n"
        "reason=stock QGKI exposes both configs; legacy-first selector hides leds-qti-flash.h while cam_flash_core still compiles QTI-specific APIs\n"
        "CANDIDATE_0047_LISA_FLASH_SELECTOR_GATE=PASS\n"
    )

original_candidate0018 = promote_lisa_qti_flash_builtin()
patch_lisa_camera_flash_selector()
try:
    base.main()
finally:
    (ROOT / "candidate-0018.ikconfig").write_bytes(original_candidate0018)

camera_obj = OUT / "techpack/camera/drivers/camera.o"
system_map = OUT / "System.map"
if not camera_obj.is_file() or camera_obj.stat().st_size == 0:
    raise SystemExit("Candidate0047 camera.o missing: common camera build did not activate")
if not system_map.is_file():
    raise SystemExit("Candidate0047 System.map missing")

sm = system_map.read_text(errors="replace")
for sym in ["cam_req_mgr_init", "cam_req_mgr_driver",
            "qti_flash_led_prepare", "qti_flash_led_set_param"]:
    if sym not in sm:
        raise SystemExit(f"Candidate0047 required built-in symbol missing: {sym}")

src_img = ROOT / "candidate-0046-Image"
src_cfg = ROOT / "candidate-0046.config"
src_ik = ROOT / "candidate-0046.ikconfig"
for p in [src_img, src_cfg, src_ik, ROOT / "boot.img"]:
    if not p.is_file() or p.stat().st_size == 0:
        raise SystemExit(f"Candidate0047 required output missing: {p.name}")
for p in [src_cfg, src_ik]:
    if "CONFIG_LEDS_QTI_FLASH=y\n" not in p.read_text(errors="replace"):
        raise SystemExit(f"Candidate0047 QTI flash was not built-in in {p.name}")

dst_img = ROOT / "candidate-0047-Image"
dst_cfg = ROOT / "candidate-0047.config"
dst_ik = ROOT / "candidate-0047.ikconfig"
shutil.copy2(src_img, dst_img)
shutil.copy2(src_cfg, dst_cfg)
shutil.copy2(src_ik, dst_ik)

camera_info = (
    "baseline=Candidate0046 A642L GPU selector repair\n"
    "primary_variable=CONFIG_USE_COMMON_CAMERA=y exported into Candidate0046 make environment\n"
    "source_mutation_relative_to_candidate0046=CONFIG_LEDS_QTI_FLASH m-to-y promotion + Lisa PM8350C QTI-over-QPNP selector\n"
    "reason=donor techpack/camera/Makefile wraps the entire camera tree in ifdef CONFIG_USE_COMMON_CAMERA\n"
    "candidate0046_config_fact=CONFIG_ARCH_LAHAINA=y CONFIG_ARCH_YUPIK=y CONFIG_QGKI=y but CONFIG_USE_COMMON_CAMERA absent\n"
    "runtime_evidence=CamX CSLInitializeHW failed to acquire requestManager and camera provider SIGABRT looped\n"
    f"camera_object_bytes={camera_obj.stat().st_size}\n"
    "cam_req_mgr_init_in_system_map=1\n"
    "cam_req_mgr_driver_in_system_map=1\n"
    "camera_linkage=built-in via donor CONFIG_SPECTRA_CAMERA=y\n"
    "qti_flash_linkage=built-in so camera IS_REACHABLE dependency is valid\n"
    "qti_flash_prepare_in_system_map=1\n"
    "qti_flash_set_param_in_system_map=1\n"
    "CANDIDATE_0047_COMMON_CAMERA_GATE=PASS\n"
)
(ROOT / "candidate-0047-camera-build.txt").write_text(camera_info)

manifest = (
    "candidate=Lisa Candidate 0047 common-camera request-manager repair\n"
    "baseline=Candidate0046\n"
    f"candidate_0047_image_sha256={sha256(dst_img)}\n"
    f"candidate_0047_boot_sha256={sha256(ROOT / 'boot.img')}\n"
    "mutation=CONFIG_USE_COMMON_CAMERA=y + CONFIG_LEDS_QTI_FLASH=y + Lisa PM8350C QTI camera flash selector\n"
    "kernel_source_mutation_relative_to_candidate0046=camera flash selector + QTI flash linkage promotion\n"
    "retained=Candidate0046 A642L GPU selector + current IPA SHMBridge guard/diagnostics\n"
    "focus=restore built-in Qualcomm camera request manager so CamX can acquire requestManager\n"
    "LISA_CANDIDATE_0047_FINAL_GATE=PASS\n"
)
(ROOT / "candidate-0047-manifest.txt").write_text(manifest)
print(camera_info)
print(manifest)
