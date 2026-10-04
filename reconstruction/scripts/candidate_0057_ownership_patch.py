"""Candidate0057: restore camera/QTI-flash/HWID module ownership.

This is an ownership-only experiment layered on the verified Candidate0056
battery-provider/UFS/raw-fault chain.  It does not claim Wi-Fi or camera runtime
success.  The runtime boot continues to use vendor modules; rebuilt modules are
compiled only to prove that the reconstructed kernel can express the same
provider split without leaving the audited provider exports in vmlinux.
"""
from pathlib import Path
import hashlib
import re
import subprocess
import types

POWER56_SHA = "170349830f264b0661b6c2358e6a3043d73f41f4"

CAMERA_DUPLICATES = (
    'cam_a5_hw_info', 'cam_a5_soc_info', 'cam_cci_dump_registers',
    'cam_cdm_acquire', 'cam_cdm_detect_hang_error', 'cam_cdm_flush_hw',
    'cam_cdm_get_iommu_handle', 'cam_cdm_handle_error', 'cam_cdm_publish_ops',
    'cam_cdm_release', 'cam_cdm_reset_hw', 'cam_cdm_stream_off',
    'cam_cdm_stream_on', 'cam_cdm_submit_bls',
    'cam_cpas_axi_util_path_type_to_string',
    'cam_cpas_axi_util_trans_type_to_string', 'cam_cpas_get_hw_info',
    'cam_cpas_is_feature_supported', 'cam_cpas_log_votes',
    'cam_cpas_notify_event', 'cam_cpas_reg_read', 'cam_cpas_reg_write',
    'cam_cpas_register_client', 'cam_cpas_select_qos_settings',
    'cam_cpas_start', 'cam_cpas_stop', 'cam_cpas_unregister_client',
    'cam_cpas_update_ahb_vote', 'cam_cpas_update_axi_vote', 'cam_custom_hw_info',
    'cam_ife_csid_hw_deinit', 'cam_ife_csid_hw_probe_init',
    'cam_mem_get_cpu_buf', 'cam_mem_get_io_buf', 'cam_mem_mgr_cache_ops',
    'cam_mem_mgr_free_memory_region', 'cam_mem_mgr_release_mem',
    'cam_mem_mgr_request_mem', 'cam_mem_mgr_reserve_memory_region',
    'cam_register_subdev', 'cam_req_mgr_init', 'cam_req_mgr_notify_message',
    'cam_res_mgr_gpio_free_arry', 'cam_res_mgr_gpio_request',
    'cam_res_mgr_gpio_set_value', 'cam_res_mgr_led_trigger_event',
    'cam_res_mgr_led_trigger_register', 'cam_res_mgr_led_trigger_unregister',
    'cam_res_mgr_util_check_if_gpio_is_shared',
    'cam_res_mgr_util_get_idx_from_shared_gpio',
    'cam_res_mgr_util_get_idx_from_shared_pctrl_gpio',
    'cam_res_mgr_util_shared_gpio_check_hold', 'cam_smmu_alloc_firmware',
    'cam_smmu_alloc_qdss', 'cam_smmu_dealloc_firmware',
    'cam_smmu_dealloc_qdss', 'cam_smmu_destroy_handle', 'cam_smmu_get_handle',
    'cam_smmu_get_iova', 'cam_smmu_get_region_info', 'cam_smmu_get_stage2_iova',
    'cam_smmu_map_kernel_iova', 'cam_smmu_map_stage2_iova',
    'cam_smmu_map_user_iova', 'cam_smmu_ops', 'cam_smmu_put_iova',
    'cam_smmu_release_sec_heap', 'cam_smmu_reserve_sec_heap',
    'cam_smmu_unmap_kernel_iova', 'cam_smmu_unmap_stage2_iova',
    'cam_smmu_unmap_user_iova', 'cam_subdev_notify_message',
    'cam_unregister_subdev',
)
HWID_DUPLICATES = (
    'get_hw_build_adc', 'get_hw_country_version', 'get_hw_id_value',
    'get_hw_project_adc', 'get_hw_version_build', 'get_hw_version_major',
    'get_hw_version_minor', 'get_hw_version_platform', 'product_name_get',
)
FLASH_DUPLICATES = ('qti_flash_led_prepare', 'qti_flash_led_set_param')
GROUPS = {
    'camera': (CAMERA_DUPLICATES, 'techpack/camera/drivers/camera'),
    'hwid': (HWID_DUPLICATES, 'drivers/misc/hwid'),
    'leds-qti-flash': (FLASH_DUPLICATES, 'drivers/leds/leds-qti-flash'),
}


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def retained(root: Path):
    """Load Candidate0056 power/UFS/fault patch with only evidence labels relabelled."""
    path = root / 'reconstruction/scripts/candidate_0056_power_patch.py'
    data = path.read_bytes()
    actual = blob_sha(data)
    if actual != POWER56_SHA:
        raise RuntimeError(f'Pinned Candidate0056 power patch changed: {actual}')
    text = data.decode().replace('0056', '0057')
    mod = types.ModuleType('candidate0057_retained_0056')
    mod.__file__ = str(path)
    exec(compile(text, str(path), 'exec'), mod.__dict__)
    return mod


def once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f'Candidate0057 {label}: anchor count={text.count(old)}')
    return text.replace(old, new, 1)


def apply(root: Path, kernel: Path) -> None:
    # First retain Candidate0056 power providers + Candidate0055 UFS + 0054 raw latch.
    retained(root).apply(root, kernel)

    # candidate_0056_power_patch copies the shared overlay file verbatim.
    # The dynamically relabelled verifier expects a 0057 runtime marker, so
    # relabel only the copied candidate source (the pinned parent file remains
    # untouched and its host-test semantics are unchanged).
    power_source = kernel / 'kernel/power/lisa_power_compat.c'
    power_text = power_source.read_text()
    power_source.write_text(once(power_text, 'LISA0056_POWER_COMPAT ready=1',
                                 'LISA0057_POWER_COMPAT ready=1',
                                 'power runtime marker'))

    cfg_path = kernel / 'out/.config'
    cfg = cfg_path.read_text()
    # The preserved Candidate0018 target is modular.  Refuse an unexpected state
    # rather than silently changing a third variable.
    for key in ('CONFIG_LEDS_QTI_FLASH', 'CONFIG_MI_HARDWARE_ID'):
        if f'{key}=m\n' not in cfg:
            raise RuntimeError(f'Candidate0057 expected preserved modular state: {key}=m')

    # CONFIG_USE_COMMON_CAMERA is intentionally still exported so the donor
    # camera sources compile for ABI/ownership validation.  Both platform
    # include files otherwise override CONFIG_SPECTRA_CAMERA back to y.
    for rel in ('techpack/camera/config/yupikcamera.conf',
                'techpack/camera/config/lahainacamera.conf'):
        path = kernel / rel
        text = path.read_text()
        path.write_text(once(text, 'export CONFIG_SPECTRA_CAMERA=y\n',
                             'export CONFIG_SPECTRA_CAMERA=m\n', rel))

    (root / 'candidate-0057-module-ownership-source.txt').write_text(
        'baseline=Candidate0056 verified boot artifact; power/UFS/proc/raw-fault/CFI/PAS/display retained\n'
        'runtime_evidence=normal vendor HWID module fails because get_hw_build_adc is already owned by vmlinux; WLAN normal branch depends on HWID\n'
        'public_reference=Jiovanni-dump/xiaomi_lisa_dump OS2.0.3 only; not claimed byte-identical to phone vendor OS2.0.8\n'
        'reference_camera_depends=leds-qti-flash only; reference camera does not import HWID\n'
        'donor_camera_difference=rebuilt donor camera directly references get_hw_version_platform for non-Lisa project conditionals\n'
        'mutation=preserve CONFIG_LEDS_QTI_FLASH=m and CONFIG_MI_HARDWARE_ID=m; force both Lahaina/Yupik camera conf CONFIG_SPECTRA_CAMERA=m while keeping common-camera source build enabled\n'
        'runtime_intent=remove audited camera/HWID/QTI-flash duplicate providers from vmlinux so vendor modules can own them\n'
        'not_claimed=WiFi repair, camera capture/flash pass, or exact stock camera module reproduction\n'
        'CANDIDATE_0057_MODULE_OWNERSHIP_SOURCE_GATE=PASS\n')


def parse_symvers(path: Path):
    out = {}
    for line in path.read_text().splitlines():
        cols = line.split()
        if len(cols) >= 3:
            out[cols[1]] = (cols[0].lower(), cols[2])
    return out


def undefined_symbols(path: Path):
    text = subprocess.check_output(['aarch64-linux-gnu-nm', '-u', str(path)], text=True)
    return {line.split()[-1] for line in text.splitlines() if line.strip()}


def module_depends(path: Path):
    raw = subprocess.check_output(['modinfo', '-F', 'depends', str(path)], text=True).strip()
    return {item for item in raw.split(',') if item}


def verify(root: Path) -> None:
    # This cascades real power-provider CRC/code checks, UFS CRC/callsite checks,
    # and the raw-fault compiled gate under Candidate0057 evidence labels.
    retained(root).verify(root)

    kernel = root / 'kernel'
    cfg = (root / 'candidate-0057.ikconfig').read_text()
    saved_cfg = (root / 'candidate-0057.config').read_text()
    for body, label in ((cfg, 'ikconfig'), (saved_cfg, 'config')):
        for token in ('CONFIG_LEDS_QTI_FLASH=m\n', 'CONFIG_MI_HARDWARE_ID=m\n'):
            if token not in body:
                raise RuntimeError(f'Candidate0057 modular ownership missing from {label}: {token.strip()}')

    for rel in ('techpack/camera/config/yupikcamera.conf',
                'techpack/camera/config/lahainacamera.conf'):
        text = (kernel / rel).read_text()
        if 'export CONFIG_SPECTRA_CAMERA=m\n' not in text or 'export CONFIG_SPECTRA_CAMERA=y\n' in text:
            raise RuntimeError(f'Candidate0057 camera platform override failed: {rel}')

    modules = {
        'camera': kernel / 'out/techpack/camera/drivers/camera.ko',
        'hwid': kernel / 'out/drivers/misc/hwid.ko',
        'leds-qti-flash': kernel / 'out/drivers/leds/leds-qti-flash.ko',
    }
    for name, path in modules.items():
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f'Candidate0057 expected rebuilt module missing: {name}: {path}')

    sm = (kernel / 'out/System.map').read_text()
    symvers = parse_symvers(kernel / 'out/Module.symvers')
    checked = 0
    ownership = []
    for group, (names, expected_owner) in GROUPS.items():
        for name in names:
            checked += 1
            if re.search(r'^[0-9a-fA-F]+\s+\S\s+' + re.escape(name) + r'$', sm, re.M):
                raise RuntimeError(f'Candidate0057 duplicate provider still linked into vmlinux: {name}')
            item = symvers.get(name)
            if not item:
                raise RuntimeError(f'Candidate0057 rebuilt provider export absent from Module.symvers: {name}')
            crc, owner = item
            if owner == 'vmlinux' or not owner.endswith(expected_owner):
                raise RuntimeError(f'Candidate0057 wrong export owner: {name}: {owner}; expected {expected_owner}')
            ownership.append(f'{group}:{name}:{crc}:{owner}')

    selector = (root / 'candidate-0057-camera-selector.txt').read_text()
    if 'CANDIDATE_0057_LISA_FLASH_SELECTOR_GATE=PASS' not in selector:
        raise RuntimeError('Candidate0057 Lisa PM8350C flash-selector gate missing')
    flash_header = (kernel / 'techpack/camera/drivers/cam_sensor_module/cam_flash/cam_flash_dev.h').read_text()
    qti_pos = flash_header.find('#if IS_REACHABLE(CONFIG_LEDS_QTI_FLASH)')
    qpnp_pos = flash_header.find('#elif IS_REACHABLE(CONFIG_LEDS_QPNP_FLASH_V2)', qti_pos)
    if qti_pos < 0 or qpnp_pos < 0 or qti_pos > qpnp_pos:
        raise RuntimeError('Candidate0057 QTI-over-QPNP Lisa flash selector did not survive')

    camera_undef = undefined_symbols(modules['camera'])
    for name in ('qti_flash_led_prepare', 'qti_flash_led_set_param', 'get_hw_version_platform'):
        if name not in camera_undef:
            raise RuntimeError(f'Candidate0057 donor camera module import not proven: {name}')
    camera_depends = module_depends(modules['camera'])
    if not {'leds-qti-flash', 'hwid'}.issubset(camera_depends):
        raise RuntimeError(f'Candidate0057 rebuilt donor camera dependency metadata unexpected: {sorted(camera_depends)}')

    # The rebuilt generic donor has CONFIG_QTI_BATTERY_CHARGER=n and an
    # inline -EINVAL fallback. It is not the stock runtime flash module.
    # Verify the actual pinned stock flash -> battery edge and CRCs instead.
    from candidate_0057_flash_contract import verify as verify_stock_flash
    verify_stock_flash(root)

    # Do not confuse the rebuilt donor camera dependency with the public stock
    # Lisa camera module.  The latter was audited as depending only on flash.
    report = (
        f'audited_duplicate_exports_removed_from_vmlinux={checked}/84\n'
        'rebuilt_modules=camera.ko,hwid.ko,leds-qti-flash.ko\n'
        f'rebuilt_donor_camera_depends={",".join(sorted(camera_depends))}\n'
        'reference_stock_camera_depends=leds-qti-flash\n'
        'reference_stock_camera_imports_hwid=0\n'
        'donor_camera_imports_qti_flash=1\n'
        'donor_camera_imports_hwid=1\n'
        'reference_stock_flash_imports_battery_provider=1\n'
        'rebuilt_donor_flash_uses_disabled_generic_charger_stub=1\n'
        'runtime_validation=pending device test\n'
        'wifi_repaired=0\n'
        'camera_runtime_validated=0\n'
        'CANDIDATE_0057_MODULE_OWNERSHIP_GATE=PASS\n'
    )
    (root / 'candidate-0057-module-ownership-verified.txt').write_text(report)
    (root / 'candidate-0057-module-export-owners.txt').write_text('\n'.join(ownership) + '\n')
    print(report, flush=True)
