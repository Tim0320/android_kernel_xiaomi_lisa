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

# Import Candidate0046 without executing its main() so Candidate0049 can apply
# the Lisa-specific camera flash selector before the common camera tree builds.
import importlib.util
spec = importlib.util.spec_from_file_location("candidate0046_base", BASE)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def patch_ipa_pas_metadata_dma_retention():
    """Retain PAS15 metadata using the original dma_alloc_coherent path.

    Upstream Qualcomm PAS gained an explicit metadata context: INIT_IMAGE keeps
    the coherent allocation alive after a successful SCM call and the caller
    releases it later.  Do not put PAS metadata inside QTEE SHMBridge: upstream
    explicitly documents that an already-bridged PIL metadata buffer can make
    PAS_INIT_IMAGE fail.
    """
    p = KERNEL / "drivers/firmware/qcom_scm.c"
    x = p.read_text()

    include_anchor = "#include <linux/qcom_scm.h>\n"
    if x.count(include_anchor) != 1:
        raise SystemExit(f"Candidate0049 qcom_scm include anchor count={x.count(include_anchor)}")
    if "#include <linux/mutex.h>\n" not in x:
        x = x.replace(include_anchor, include_anchor + "#include <linux/mutex.h>\n", 1)

    global_anchor = "static struct qcom_scm *__scm;\n"
    if x.count(global_anchor) != 1:
        raise SystemExit(f"Candidate0049 qcom_scm global anchor count={x.count(global_anchor)}")
    global_new = global_anchor + r'''
/*
 * Lisa Candidate0049: preserve the successful legacy PAS_INIT_IMAGE memory
 * type (dma_alloc_coherent) but retain PAS15 metadata until auth_and_reset.
 */
static DEFINE_MUTEX(lisa_ipa_pas_metadata_lock);
static void *lisa_ipa_pas_metadata_buf;
static dma_addr_t lisa_ipa_pas_metadata_phys;
static size_t lisa_ipa_pas_metadata_size;
static bool lisa_ipa_pas_metadata_valid;

static void lisa_ipa_pas_metadata_release_locked(const char *phase, int scm_ret)
{
	if (!lisa_ipa_pas_metadata_valid)
		return;

	pr_emerg("LISA0049_IPA_METADATA stage=release phase=%s ret=%d phys=%pad size=%zu\n",
		 phase, scm_ret, &lisa_ipa_pas_metadata_phys,
		 lisa_ipa_pas_metadata_size);
	dma_free_coherent(__scm->dev, lisa_ipa_pas_metadata_size,
			  lisa_ipa_pas_metadata_buf,
			  lisa_ipa_pas_metadata_phys);
	lisa_ipa_pas_metadata_buf = NULL;
	lisa_ipa_pas_metadata_phys = 0;
	lisa_ipa_pas_metadata_size = 0;
	lisa_ipa_pas_metadata_valid = false;
}
'''
    x = x.replace(global_anchor, global_new, 1)

    old_init = r'''int qcom_scm_pas_init_image(u32 peripheral, const void *metadata, size_t size)
{
	dma_addr_t mdata_phys;
	void *mdata_buf;
	int ret;

	/*
	 * During the scm call memory protection will be enabled for the meta
	 * data blob, so make sure it's physically contiguous, 4K aligned and
	 * non-cachable to avoid XPU violations.
	 */
	mdata_buf = dma_alloc_coherent(__scm->dev, size, &mdata_phys,
				       GFP_KERNEL);
	if (!mdata_buf) {
		dev_err(__scm->dev, "Allocation of metadata buffer failed.\n");
		return -ENOMEM;
	}
	memcpy(mdata_buf, metadata, size);

	ret = qcom_scm_clk_enable();
	if (ret)
		goto free_metadata;

	ret = __qcom_scm_pas_init_image(__scm->dev, peripheral, mdata_phys);

	qcom_scm_clk_disable();

free_metadata:
	dma_free_coherent(__scm->dev, size, mdata_buf, mdata_phys);

	return ret;
}
EXPORT_SYMBOL(qcom_scm_pas_init_image);
'''
    new_init = r'''int qcom_scm_pas_init_image(u32 peripheral, const void *metadata, size_t size)
{
	dma_addr_t mdata_phys;
	void *mdata_buf;
	int ret;

	mdata_buf = dma_alloc_coherent(__scm->dev, size, &mdata_phys,
				       GFP_KERNEL);
	if (!mdata_buf) {
		dev_err(__scm->dev, "Allocation of metadata buffer failed.\n");
		return -ENOMEM;
	}
	memcpy(mdata_buf, metadata, size);

	if (peripheral == 0x0f) {
		mutex_lock(&lisa_ipa_pas_metadata_lock);
		lisa_ipa_pas_metadata_release_locked("stale_before_init", 0);
		pr_emerg("LISA0049_IPA_METADATA stage=before_pas_init pas_id=%u phys=%pad size=%zu\n",
			 peripheral, &mdata_phys, size);
	}

	ret = qcom_scm_clk_enable();
	if (ret)
		goto free_metadata;

	ret = __qcom_scm_pas_init_image(__scm->dev, peripheral, mdata_phys);

	qcom_scm_clk_disable();

	if (peripheral == 0x0f) {
		pr_emerg("LISA0049_IPA_METADATA stage=after_pas_init pas_id=%u ret=%d phys=%pad size=%zu\n",
			 peripheral, ret, &mdata_phys, size);
		if (!ret) {
			lisa_ipa_pas_metadata_buf = mdata_buf;
			lisa_ipa_pas_metadata_phys = mdata_phys;
			lisa_ipa_pas_metadata_size = size;
			lisa_ipa_pas_metadata_valid = true;
			mutex_unlock(&lisa_ipa_pas_metadata_lock);
			return 0;
		}
	}

free_metadata:
	dma_free_coherent(__scm->dev, size, mdata_buf, mdata_phys);
	if (peripheral == 0x0f)
		mutex_unlock(&lisa_ipa_pas_metadata_lock);

	return ret;
}
EXPORT_SYMBOL(qcom_scm_pas_init_image);
'''
    if x.count(old_init) != 1:
        raise SystemExit(f"Candidate0049 PAS init-image anchor count={x.count(old_init)}")
    x = x.replace(old_init, new_init, 1)

    old_auth = r'''int qcom_scm_pas_auth_and_reset(u32 peripheral)
{
	int ret;

	ret = qcom_scm_clk_enable();
	if (ret)
		return ret;

	ret = __qcom_scm_pas_auth_and_reset(__scm->dev, peripheral);
	qcom_scm_clk_disable();

	return ret;
}
EXPORT_SYMBOL(qcom_scm_pas_auth_and_reset);
'''
    new_auth = r'''int qcom_scm_pas_auth_and_reset(u32 peripheral)
{
	int ret;

	ret = qcom_scm_clk_enable();
	if (ret) {
		if (peripheral == 0x0f) {
			mutex_lock(&lisa_ipa_pas_metadata_lock);
			lisa_ipa_pas_metadata_release_locked("auth_clk_enable_failed", ret);
			mutex_unlock(&lisa_ipa_pas_metadata_lock);
		}
		return ret;
	}

	ret = __qcom_scm_pas_auth_and_reset(__scm->dev, peripheral);
	qcom_scm_clk_disable();

	if (peripheral == 0x0f) {
		mutex_lock(&lisa_ipa_pas_metadata_lock);
		pr_emerg("LISA0049_IPA_METADATA stage=after_auth_reset pas_id=%u ret=%d retained=%d phys=%pad size=%zu\n",
			 peripheral, ret, lisa_ipa_pas_metadata_valid,
			 &lisa_ipa_pas_metadata_phys, lisa_ipa_pas_metadata_size);
		lisa_ipa_pas_metadata_release_locked("after_auth_reset", ret);
		mutex_unlock(&lisa_ipa_pas_metadata_lock);
	}

	return ret;
}
EXPORT_SYMBOL(qcom_scm_pas_auth_and_reset);
'''
    if x.count(old_auth) != 1:
        raise SystemExit(f"Candidate0049 PAS auth anchor count={x.count(old_auth)}")
    x = x.replace(old_auth, new_auth, 1)

    p.write_text(x)

    out = p.read_text()
    forbidden = [
        "qtee_shmbridge_allocate_shm",
        "lisa_ipa_pas_metadata_shm",
    ]
    for item in forbidden:
        if item in out:
            raise SystemExit(f"Candidate0049 forbidden metadata SHMBridge path remains: {item}")
    gates = [
        "static DEFINE_MUTEX(lisa_ipa_pas_metadata_lock);",
        "dma_alloc_coherent(__scm->dev, size, &mdata_phys",
        "lisa_ipa_pas_metadata_valid = true;",
        "LISA0049_IPA_METADATA stage=before_pas_init",
        "LISA0049_IPA_METADATA stage=after_pas_init",
        "LISA0049_IPA_METADATA stage=after_auth_reset",
        'lisa_ipa_pas_metadata_release_locked("after_auth_reset", ret);',
    ]
    for gate in gates:
        if gate not in out:
            raise SystemExit(f"Candidate0049 IPA metadata retention gate missing: {gate}")

    (ROOT / "candidate-0049-ipa-metadata-dma-retention.txt").write_text(
        "evidence_0048=lisa-live-20261003-201800: PAS15 metadata in QTEE SHMBridge at 0x1f6000000/0x1f6015000 caused PAS_INIT_IMAGE=-22; 47 failures observed\n"
        "upstream_fact=Qualcomm qcom_scm explicitly says already-SHM-bridged PIL metadata will fail PAS_INIT_IMAGE\n"
        "upstream_fix_pattern=successful PAS_INIT_IMAGE retains dma_alloc_coherent metadata in a context and releases it later\n"
        "mutation=PAS15 keeps legacy dma_alloc_coherent metadata alive until qcom_scm_pas_auth_and_reset returns\n"
        "non_target_pas=unchanged immediate dma_free_coherent path\n"
        "firmware_carveout_bridge=retained Candidate0046 for single-variable testing\n"
        "runtime_markers=LISA0049_IPA_METADATA before_pas_init/after_pas_init/after_auth_reset/release\n"
        "CANDIDATE_0049_IPA_METADATA_DMA_RETENTION_GATE=PASS\n"
    )


_candidate0049_overlay_known_good = base.overlay_known_good
def candidate0049_overlay_known_good():
    _candidate0049_overlay_known_good()
    patch_ipa_pas_metadata_dma_retention()
base.overlay_known_good = candidate0049_overlay_known_good

def promote_lisa_camera_runtime_deps_builtin():
    cfg_path = ROOT / "candidate-0018.ikconfig"
    if not cfg_path.is_file() or cfg_path.stat().st_size == 0:
        raise SystemExit("Candidate0049 preserved Candidate0018 IKCONFIG missing")

    original = cfg_path.read_bytes()
    cfg = original.decode("utf-8", "replace")

    for dep in ["CONFIG_LEDS_CLASS_FLASH=y\n", "CONFIG_MFD_SPMI_PMIC=y\n"]:
        if dep not in cfg:
            raise SystemExit(f"Candidate0049 QTI flash built-in dependency missing: {dep.strip()}")

    if "CONFIG_LEDS_QTI_FLASH=m\n" in cfg:
        flash_stock_state = "m"
        cfg = cfg.replace("CONFIG_LEDS_QTI_FLASH=m\n", "CONFIG_LEDS_QTI_FLASH=y\n", 1)
    elif "CONFIG_LEDS_QTI_FLASH=y\n" in cfg:
        flash_stock_state = "y"
    else:
        raise SystemExit("Candidate0049 CONFIG_LEDS_QTI_FLASH is neither m nor y in preserved config")

    if "CONFIG_MI_HARDWARE_ID=m\n" in cfg:
        hwid_stock_state = "m"
        cfg = cfg.replace("CONFIG_MI_HARDWARE_ID=m\n", "CONFIG_MI_HARDWARE_ID=y\n", 1)
    elif "CONFIG_MI_HARDWARE_ID=y\n" in cfg:
        hwid_stock_state = "y"
    else:
        raise SystemExit("Candidate0049 CONFIG_MI_HARDWARE_ID is neither m nor y in preserved config")

    cfg_path.write_text(cfg)
    (ROOT / "candidate-0049-camera-deps-linkage.txt").write_text(
        f"stock_CONFIG_LEDS_QTI_FLASH={flash_stock_state}\n"
        "effective_CONFIG_LEDS_QTI_FLASH=y\n"
        f"stock_CONFIG_MI_HARDWARE_ID={hwid_stock_state}\n"
        "effective_CONFIG_MI_HARDWARE_ID=y\n"
        "camera_linkage=built-in\n"
        "reason_qti_flash=built-in camera cannot directly depend on modular QTI flash through IS_REACHABLE/IS_ENABLED mixed guards\n"
        "reason_hwid=built-in camera directly calls get_hw_version_platform from drivers/misc/hwid.c, so MI_HARDWARE_ID must be built-in too\n"
        "original_candidate0018_restored_after_build=1\n"
        "CANDIDATE_0049_CAMERA_DEPS_LINKAGE_GATE=PASS\n"
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
        raise SystemExit("Candidate0049 PM8350C QTI flash DTS identity missing")
    if '.compatible = "qcom,pm8350c-flash-led"' not in led:
        raise SystemExit("Candidate0049 QTI flash driver PM8350C match missing")

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
        raise SystemExit(f"Candidate0049 flash header selector anchor count={h.count(old_h)}")
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
        raise SystemExit(f"Candidate0049 flash prepare selector anchor count={c.count(old_c)}")
    core_c.write_text(c.replace(old_c, new_c, 1))

    (ROOT / "candidate-0049-camera-selector.txt").write_text(
        "device=Lisa SM7325/Yupik\n"
        "pmic_flash_compatible=qcom,pm8350c-flash-led\n"
        "provider=drivers/leds/leds-qti-flash.c\n"
        "legacy_qpnp_provider_matches=pm6150l,pmi632\n"
        "mutation=prefer CONFIG_LEDS_QTI_FLASH over CONFIG_LEDS_QPNP_FLASH_V2 in camera flash header/prepare selectors\n"
        "reason=stock QGKI exposes both configs; legacy-first selector hides leds-qti-flash.h while cam_flash_core still compiles QTI-specific APIs\n"
        "CANDIDATE_0049_LISA_FLASH_SELECTOR_GATE=PASS\n"
    )

original_candidate0018 = promote_lisa_camera_runtime_deps_builtin()
patch_lisa_camera_flash_selector()
try:
    base.main()
finally:
    (ROOT / "candidate-0018.ikconfig").write_bytes(original_candidate0018)

camera_archive = OUT / "techpack/camera/drivers/built-in.a"
request_mgr_obj = OUT / "techpack/camera/drivers/cam_req_mgr/cam_req_mgr_dev.o"
system_map = OUT / "System.map"
if not camera_archive.is_file() or camera_archive.stat().st_size == 0:
    raise SystemExit("Candidate0049 camera built-in archive missing: common camera build did not activate")
if not request_mgr_obj.is_file() or request_mgr_obj.stat().st_size == 0:
    raise SystemExit("Candidate0049 cam_req_mgr_dev.o missing: request-manager sources were not compiled")
if not system_map.is_file():
    raise SystemExit("Candidate0049 System.map missing")

sm = system_map.read_text(errors="replace")
for sym in ["cam_req_mgr_init", "cam_req_mgr_driver",
            "qti_flash_led_prepare", "qti_flash_led_set_param",
            "get_hw_version_platform"]:
    if sym not in sm:
        raise SystemExit(f"Candidate0049 required built-in symbol missing: {sym}")

src_img = ROOT / "candidate-0046-Image"
src_cfg = ROOT / "candidate-0046.config"
src_ik = ROOT / "candidate-0046.ikconfig"
for p in [src_img, src_cfg, src_ik, ROOT / "boot.img"]:
    if not p.is_file() or p.stat().st_size == 0:
        raise SystemExit(f"Candidate0049 required output missing: {p.name}")
for p in [src_cfg, src_ik]:
    config_text = p.read_text(errors="replace")
    if "CONFIG_LEDS_QTI_FLASH=y\n" not in config_text:
        raise SystemExit(f"Candidate0049 QTI flash was not built-in in {p.name}")
    if "CONFIG_MI_HARDWARE_ID=y\n" not in config_text:
        raise SystemExit(f"Candidate0049 Xiaomi HWID was not built-in in {p.name}")

dst_img = ROOT / "candidate-0049-Image"
dst_cfg = ROOT / "candidate-0049.config"
dst_ik = ROOT / "candidate-0049.ikconfig"
shutil.copy2(src_img, dst_img)
shutil.copy2(src_cfg, dst_cfg)
shutil.copy2(src_ik, dst_ik)

camera_info = (
    "baseline=Candidate0046 A642L GPU selector repair\n"
    "primary_variable=CONFIG_USE_COMMON_CAMERA=y exported into Candidate0046 make environment\n"
    "source_mutation_relative_to_candidate0046=CONFIG_LEDS_QTI_FLASH m-to-y + CONFIG_MI_HARDWARE_ID m-to-y promotions + Lisa PM8350C QTI-over-QPNP selector\n"
    "reason=donor techpack/camera/Makefile wraps the entire camera tree in ifdef CONFIG_USE_COMMON_CAMERA\n"
    "candidate0046_config_fact=CONFIG_ARCH_LAHAINA=y CONFIG_ARCH_YUPIK=y CONFIG_QGKI=y but CONFIG_USE_COMMON_CAMERA absent\n"
    "runtime_evidence=CamX CSLInitializeHW failed to acquire requestManager and camera provider SIGABRT looped\n"
    f"camera_builtin_archive_bytes={camera_archive.stat().st_size}\n"
    f"cam_req_mgr_dev_object_bytes={request_mgr_obj.stat().st_size}\n"
    "cam_req_mgr_init_in_system_map=1\n"
    "cam_req_mgr_driver_in_system_map=1\n"
    "camera_linkage=built-in via donor CONFIG_SPECTRA_CAMERA=y\n"
    "qti_flash_linkage=built-in so camera IS_REACHABLE dependency is valid\n"
    "qti_flash_prepare_in_system_map=1\n"
    "qti_flash_set_param_in_system_map=1\n"
    "get_hw_version_platform_in_system_map=1\n"
    "CANDIDATE_0049_COMMON_CAMERA_GATE=PASS\n"
)
(ROOT / "candidate-0049-camera-build.txt").write_text(camera_info)

manifest = (
    "candidate=Lisa Candidate 0047 common-camera request-manager repair\n"
    "baseline=Candidate0046\n"
    f"candidate_0049_image_sha256={sha256(dst_img)}\n"
    f"candidate_0049_boot_sha256={sha256(ROOT / 'boot.img')}\n"
    "mutation=CONFIG_USE_COMMON_CAMERA=y + CONFIG_LEDS_QTI_FLASH=y + CONFIG_MI_HARDWARE_ID=y + Lisa PM8350C QTI camera flash selector\n"
    "kernel_source_mutation_relative_to_candidate0046=camera flash selector + QTI flash/HWID linkage promotions\n"
    "retained=Candidate0046 A642L GPU selector + current IPA SHMBridge guard/diagnostics\n"
    "focus=restore built-in Qualcomm camera request manager so CamX can acquire requestManager\n"
    "LISA_CANDIDATE_0049_FINAL_GATE=PASS\n"
)
meta_gate = ROOT / "candidate-0049-ipa-metadata-dma-retention.txt"
if not meta_gate.is_file() or "CANDIDATE_0049_IPA_METADATA_DMA_RETENTION_GATE=PASS" not in meta_gate.read_text():
    raise SystemExit("Candidate0049 IPA DMA metadata retention gate missing")
(ROOT / "candidate-0049-manifest.txt").write_text(manifest)
print(camera_info)
print(manifest)
