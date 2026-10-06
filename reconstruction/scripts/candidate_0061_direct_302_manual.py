#!/usr/bin/env python3
from pathlib import Path

import candidate_0061_batch_a_manual as batch_a
import candidate_0061_batch_b_manual as batch_b


def once(s: str, old: str, new: str, label: str) -> str:
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: anchor count={n}")
    return s.replace(old, new, 1)


def ensure_once_after(s: str, anchor: str, addition: str, label: str) -> str:
    if addition in s:
        return s
    return once(s, anchor, anchor + addition, label)


def adapt_makefile(root: Path):
    p = root / "Makefile"
    s = p.read_text()

    # Final release identity. Never reuse the retired Batch-B 292->296-only adapter.
    for old in ("SUBLEVEL = 289\n", "SUBLEVEL = 292\n", "SUBLEVEL = 296\n", "SUBLEVEL = 299\n"):
        if old in s:
            s = s.replace(old, "SUBLEVEL = 302\n", 1)
            break
    if "SUBLEVEL = 302\n" not in s:
        raise RuntimeError("Direct-302 Makefile: cannot establish SUBLEVEL=302")

    # Stable C endpoint: propagate CLANG_FLAGS through preprocessor flags while
    # preserving Lisa's downstream Clang-11 target/prefix/no-integrated-as setup.
    old = "KBUILD_CFLAGS\t+= $(CLANG_FLAGS)\nKBUILD_AFLAGS\t+= $(CLANG_FLAGS)\n"
    if old in s:
        s = s.replace(old, "KBUILD_CPPFLAGS\t+= $(CLANG_FLAGS)\n", 1)
    elif "KBUILD_CPPFLAGS\t+= $(CLANG_FLAGS)\n" not in s:
        raise RuntimeError("Direct-302 Makefile: CLANG_FLAGS propagation anchor missing")

    # Stable B endpoint: suppress warning added by newer clang, without importing
    # MiYume's newer LLVM plumbing or custom optimization policy.
    warning = "KBUILD_CFLAGS += $(call cc-disable-warning, default-const-init-unsafe)\n"
    if warning not in s:
        anchors = [
            "KBUILD_CFLAGS += $(call cc-disable-warning, undefined-optimized)\n",
            "KBUILD_CFLAGS += -Wno-tautological-compare\n",
        ]
        for anchor in anchors:
            if anchor in s:
                s = s.replace(anchor, anchor + warning, 1)
                break
        else:
            raise RuntimeError("Direct-302 Makefile: warning insertion anchor missing")

    # Stable B endpoint.
    builtin = "KBUILD_CFLAGS += -fno-builtin-wcslen\n"
    if builtin not in s:
        anchor = "KBUILD_CFLAGS\t+= $(call cc-option,-fmacro-prefix-map=$(srctree)/=)\n"
        if anchor not in s:
            raise RuntimeError("Direct-302 Makefile: fmacro-prefix-map anchor missing")
        s = s.replace(anchor, builtin + "\n" + anchor, 1)

    # Stable A endpoint: use clang's linker path for userspace helper links.
    userld = "KBUILD_USERLDFLAGS += $(call cc-option, --ld-path=$(LD))\n"
    if userld not in s:
        anchor = "KBUILD_LDFLAGS += $(KCPPFLAGS)\n"
        if anchor in s:
            s = s.replace(anchor, anchor + userld, 1)
        else:
            # Upstream places this near final user flags; keep Lisa layout and add
            # immediately before the first scripts/Makefile.* include as a safe,
            # toolchain-local insertion point.
            marker = "include scripts/Makefile.kasan\n"
            if marker not in s:
                raise RuntimeError("Direct-302 Makefile: userld insertion anchor missing")
            s = s.replace(marker, userld + "\n" + marker, 1)

    p.write_text(s)



def adapt_cputype(root: Path):
    p = root / "arch/arm64/include/asm/cputype.h"
    s = p.read_text()

    # Segment B endpoint: Cortex-A76AE. Lisa already carries a downstream CPU-ID
    # superset (including Kryo and later Arm parts), so only insert the stable IDs.
    if "ARM_CPU_PART_CORTEX_A76AE" not in s:
        anchor = "#define ARM_CPU_PART_CORTEX_A77\t\t0xD0D\n"
        s = once(
            s, anchor,
            anchor + "#define ARM_CPU_PART_CORTEX_A76AE\t0xD0E\n",
            "Direct-302 Cortex-A76AE part",
        )
    if "MIDR_CORTEX_A76AE" not in s:
        anchor = "#define MIDR_CORTEX_A77\tMIDR_CPU_MODEL(ARM_CPU_IMP_ARM, ARM_CPU_PART_CORTEX_A77)\n"
        s = once(
            s, anchor,
            anchor + "#define MIDR_CORTEX_A76AE\tMIDR_CPU_MODEL(ARM_CPU_IMP_ARM, ARM_CPU_PART_CORTEX_A76AE)\n",
            "Direct-302 Cortex-A76AE MIDR",
        )

    # Segment D endpoint: Neoverse-V3AE. These hunks currently apply cleanly in
    # the one-shot patch, but enforce the final state in case downstream context
    # changes so the Direct-302 adapter remains self-contained.
    if "ARM_CPU_PART_NEOVERSE_V3AE" not in s:
        anchor = "#define ARM_CPU_PART_NEOVERSE_V3\t0xD84\n"
        if anchor not in s:
            raise RuntimeError("Direct-302 Neoverse-V3AE part anchor missing")
        s = s.replace(anchor, "#define ARM_CPU_PART_NEOVERSE_V3AE\t0xD83\n" + anchor, 1)
    if "MIDR_NEOVERSE_V3AE" not in s:
        anchor = "#define MIDR_NEOVERSE_V3 MIDR_CPU_MODEL(ARM_CPU_IMP_ARM, ARM_CPU_PART_NEOVERSE_V3)\n"
        if anchor not in s:
            raise RuntimeError("Direct-302 Neoverse-V3AE MIDR anchor missing")
        s = s.replace(
            anchor,
            "#define MIDR_NEOVERSE_V3AE\tMIDR_CPU_MODEL(ARM_CPU_IMP_ARM, ARM_CPU_PART_NEOVERSE_V3AE)\n" + anchor,
            1,
        )

    # Preserve Lisa's downstream Qualcomm/Kryo IDs; only assert the stable
    # endpoint additions required by B+D provenance.
    for token in (
        "ARM_CPU_PART_CORTEX_A76AE",
        "MIDR_CORTEX_A76AE",
        "ARM_CPU_PART_NEOVERSE_V3AE",
        "MIDR_NEOVERSE_V3AE",
    ):
        if token not in s:
            raise RuntimeError(f"Direct-302 cputype endpoint missing {token}")

    p.write_text(s)


def adapt_hid_ids(root: Path):
    p = root / "drivers/hid/hid-ids.h"
    s = p.read_text()

    # Segment A: Quanta HP 5MP identity.
    token = "#define USB_DEVICE_ID_QUANTA_HP_5MP_CAMERA_5473\t\t0x5473\n"
    if token not in s:
        anchor = "#define USB_DEVICE_ID_QUANTA_OPTICAL_TOUCH_3008\t\t0x3008\n"
        s = once(s, anchor, anchor + token, "Direct-302 Quanta HP 5MP HID ID")

    # Segment B: ADATA XPG wireless gaming mouse identities.
    adata = (
        "#define USB_VENDOR_ID_ADATA_XPG 0x125f\n"
        "#define USB_DEVICE_ID_ADATA_XPG_WL_GAMING_MOUSE 0x7505\n"
        "#define USB_DEVICE_ID_ADATA_XPG_WL_GAMING_MOUSE_DONGLE 0x7506\n"
    )
    if "#define USB_VENDOR_ID_ADATA_XPG 0x125f\n" not in s:
        anchor = "#define USB_VENDOR_ID_ACTIONSTAR\t0x2101\n#define USB_DEVICE_ID_ACTIONSTAR_1011\t0x1011\n"
        s = once(s, anchor, anchor + "\n" + adata, "Direct-302 ADATA XPG HID IDs")

    # Segment B: Chicony HP 5MP camera identities.
    chicony = (
        "#define USB_DEVICE_ID_CHICONY_HP_5MP_CAMERA\t0xb824\n"
        "#define USB_DEVICE_ID_CHICONY_HP_5MP_CAMERA2\t0xb82c\n"
    )
    if "#define USB_DEVICE_ID_CHICONY_HP_5MP_CAMERA\t0xb824\n" not in s:
        anchor = "#define USB_DEVICE_ID_CHICONY_ACER_SWITCH12\t0x1421\n"
        s = once(s, anchor, anchor + chicony, "Direct-302 Chicony HP 5MP HID IDs")

    # Segment D: Cooler Master wireless mouse dongle.
    cooler = (
        "#define USB_VENDOR_ID_COOLER_MASTER\t0x2516\n"
        "#define USB_DEVICE_ID_COOLER_MASTER_MICE_DONGLE\t0x01b7\n"
    )
    if "#define USB_VENDOR_ID_COOLER_MASTER\t0x2516\n" not in s:
        anchor = "#define USB_VENDOR_ID_CODEMERCS\t\t0x07c0\n#define USB_DEVICE_ID_CODEMERCS_IOW_FIRST\t0x1500\n#define USB_DEVICE_ID_CODEMERCS_IOW_LAST\t0x15ff\n"
        s = once(s, anchor, anchor + "\n" + cooler, "Direct-302 Cooler Master HID IDs")

    # Final 5.4.302 endpoint names 0x4c4a:0x4155 as Jieli SDK. If an
    # intermediate Segment-B SMARTLINKTECHNOLOGY spelling is present, rename it
    # instead of keeping duplicate IDs.
    s = s.replace(
        "#define USB_VENDOR_ID_SMARTLINKTECHNOLOGY              0x4c4a\n"
        "#define USB_DEVICE_ID_SMARTLINKTECHNOLOGY_4155         0x4155\n",
        "#define USB_VENDOR_ID_JIELI_SDK_DEFAULT\t\t0x4c4a\n"
        "#define USB_DEVICE_ID_JIELI_SDK_4155\t\t0x4155\n",
    )
    if "#define USB_VENDOR_ID_JIELI_SDK_DEFAULT\t\t0x4c4a\n" not in s:
        # Lisa/Xiaomi carries QVR/NREAL downstream IDs here. MiYume 5.4.302
        # confirms they remain and Jieli follows them before Qualcomm-local IDs.
        anchor = (
            "#define USB_VENDOR_ID_QVR5\t0x045e\n"
            "#define USB_VENDOR_ID_QVR32A\t0x04b4\n"
            "#define USB_VENDOR_ID_NREAL\t0x05a9\n"
            "#define USB_DEVICE_ID_QVR5\t0x0659\n"
            "#define USB_DEVICE_ID_QVR32A\t0x00c3\n"
            "#define USB_DEVICE_ID_NREAL\t0x0680\n"
        )
        jieli = (
            "\n#define USB_VENDOR_ID_JIELI_SDK_DEFAULT\t\t0x4c4a\n"
            "#define USB_DEVICE_ID_JIELI_SDK_4155\t\t0x4155\n"
        )
        s = once(s, anchor, anchor + jieli, "Direct-302 Jieli SDK HID IDs")

    for token in (
        "USB_DEVICE_ID_QUANTA_HP_5MP_CAMERA_5473",
        "USB_VENDOR_ID_ADATA_XPG",
        "USB_DEVICE_ID_CHICONY_HP_5MP_CAMERA",
        "USB_VENDOR_ID_COOLER_MASTER",
        "USB_VENDOR_ID_JIELI_SDK_DEFAULT",
        "USB_DEVICE_ID_JIELI_SDK_4155",
        "USB_VENDOR_ID_QVR5",
        "USB_VENDOR_ID_NREAL",
    ):
        if token not in s:
            raise RuntimeError(f"Direct-302 HID endpoint missing {token}")

    if "USB_VENDOR_ID_SMARTLINKTECHNOLOGY" in s or "USB_DEVICE_ID_SMARTLINKTECHNOLOGY_4155" in s:
        raise RuntimeError("Direct-302 HID endpoint retained intermediate Smartlink naming")

    p.write_text(s)



def adapt_ivtv_streams(root: Path):
    p = root / "drivers/media/pci/ivtv/ivtv-streams.c"
    s = p.read_text()

    # Segment D 5.4.299->5.4.302 is exactly the PCI DMA direction enum
    # API rename in this file. Preserve Lisa's downstream VFL_TYPE_GRABBER
    # layout and apply only the stable DMA endpoint semantics.
    replacements = (
        ("PCI_DMA_FROMDEVICE", "DMA_FROM_DEVICE"),
        ("PCI_DMA_TODEVICE", "DMA_TO_DEVICE"),
        ("PCI_DMA_NONE", "DMA_NONE"),
    )
    for old, new in replacements:
        s = s.replace(old, new)

    for old, _ in replacements:
        if old in s:
            raise RuntimeError(f"Direct-302 ivtv endpoint retained {old}")

    expected = {
        "DMA_FROM_DEVICE": 4,
        "DMA_TO_DEVICE": 2,
        "DMA_NONE": 5,
    }
    for token, count in expected.items():
        actual = s.count(token)
        if actual != count:
            raise RuntimeError(
                f"Direct-302 ivtv endpoint {token} count={actual}, expected={count}"
            )

    # Lisa intentionally carries the downstream VFL_TYPE_GRABBER naming.
    if s.count("VFL_TYPE_GRABBER") < 4:
        raise RuntimeError("Direct-302 ivtv endpoint lost Lisa VFL_TYPE_GRABBER layout")

    p.write_text(s)



def adapt_sdhci_msm(root: Path):
    p = root / "drivers/mmc/host/sdhci-msm.c"
    s = p.read_text()

    # Segment D 5.4.299->5.4.302: add SDR50 tuning support. MiYume 5.4.302
    # confirms the same endpoint integrated into the downstream Qualcomm flow.
    macro = "#define CORE_HC_SELECT_IN_SDR50\t(4 << 19)\n"
    if macro not in s:
        anchor = "#define CORE_HC_SELECT_IN_EN\tBIT(18)\n"
        s = once(s, anchor, anchor + macro, "Direct-302 SDR50 select macro")

    tuning_gate = (
        "\tif (ios->timing == MMC_TIMING_UHS_SDR50 &&\n"
        "\t    host->flags & SDHCI_SDR50_NEEDS_TUNING)\n"
        "\t\treturn true;\n\n"
    )
    if tuning_gate not in s:
        anchor = (
            "static bool sdhci_msm_is_tuning_needed(struct sdhci_host *host)\n"
            "{\n"
            "\tstruct mmc_ios *ios = &host->mmc->ios;\n\n"
        )
        s = once(
            s, anchor, anchor + tuning_gate,
            "Direct-302 SDR50 tuning-needed gate",
        )

    start = s.find("static int sdhci_msm_execute_tuning")
    if start < 0:
        raise RuntimeError("Direct-302 sdhci-msm execute_tuning function missing")
    head = s[start:start + 1000]
    if "\tu32 config;\n" not in head:
        anchor = (
            "\tstruct mmc_ios ios = host->mmc->ios;\n"
            "\tu32 core_vendor_spec;\n"
            "\tstruct sdhci_pltfm_host *pltfm_host = sdhci_priv(host);\n"
        )
        replacement = (
            "\tstruct mmc_ios ios = host->mmc->ios;\n"
            "\tu32 core_vendor_spec;\n"
            "\tu32 config;\n"
            "\tstruct sdhci_pltfm_host *pltfm_host = sdhci_priv(host);\n"
        )
        s = once(
            s, anchor, replacement,
            "Direct-302 SDR50 tuning config variable",
        )

    select = (
        "\tif (ios.timing == MMC_TIMING_UHS_SDR50 &&\n"
        "\t    host->flags & SDHCI_SDR50_NEEDS_TUNING) {\n"
        "\t\tconfig = readl_relaxed(host->ioaddr + msm_offset->core_vendor_spec);\n"
        "\t\tconfig &= ~CORE_HC_SELECT_IN_MASK;\n"
        "\t\tconfig |= CORE_HC_SELECT_IN_EN | CORE_HC_SELECT_IN_SDR50;\n"
        "\t\twritel_relaxed(config, host->ioaddr + msm_offset->core_vendor_spec);\n"
        "\t}\n\n"
    )
    if select not in s:
        anchor = "\tmsm_host->tuning_done = 0;\n\n"
        s = once(
            s, anchor, anchor + select,
            "Direct-302 SDR50 tuning vendor-select",
        )

    for token in (
        "CORE_HC_SELECT_IN_SDR50",
        "SDHCI_SDR50_NEEDS_TUNING",
        "CORE_HC_SELECT_IN_EN | CORE_HC_SELECT_IN_SDR50",
    ):
        if token not in s:
            raise RuntimeError(f"Direct-302 sdhci-msm endpoint missing {token}")

    p.write_text(s)



def adapt_platform_kconfig(root: Path):
    p = root / "drivers/platform/Kconfig"
    s = p.read_text()
    surface = 'source "drivers/platform/surface/Kconfig"\n'
    msm = 'source "drivers/platform/msm/Kconfig"\n'

    if msm not in s:
        raise RuntimeError("Direct-302 platform Kconfig: Lisa MSM source missing")

    if surface not in s:
        s = once(
            s,
            msm,
            surface + "\n" + msm,
            "Direct-302 platform Kconfig Surface before MSM",
        )

    if s.count(surface) != 1 or s.count(msm) != 1:
        raise RuntimeError(
            f"Direct-302 platform Kconfig: expected one Surface and one MSM source "
            f"(surface={s.count(surface)}, msm={s.count(msm)})"
        )
    if s.index(surface) > s.index(msm):
        raise RuntimeError("Direct-302 platform Kconfig: Surface must precede MSM")

    p.write_text(s)


def adapt_platform_makefile(root: Path):
    p = root / "drivers/platform/Makefile"
    s = p.read_text()
    surface = "obj-$(CONFIG_SURFACE_PLATFORMS)\t+= surface/\n"
    msm = "obj-$(CONFIG_ARCH_QCOM)\t\t+= msm/\n"

    if msm not in s:
        raise RuntimeError("Direct-302 platform Makefile: Lisa QCOM msm entry missing")

    if surface not in s:
        s = once(
            s,
            msm,
            surface + msm,
            "Direct-302 platform Makefile Surface before QCOM msm",
        )

    if s.count(surface) != 1 or s.count(msm) != 1:
        raise RuntimeError(
            f"Direct-302 platform Makefile: expected one Surface and one QCOM msm entry "
            f"(surface={s.count(surface)}, msm={s.count(msm)})"
        )
    if s.index(surface) > s.index(msm):
        raise RuntimeError("Direct-302 platform Makefile: Surface must precede QCOM msm")

    p.write_text(s)


def adapt_rpmh_rsc(root: Path):
    p = root / "drivers/soc/qcom/rpmh-rsc.c"
    s = p.read_text()

    old = (
        "\t\t/*\n"
        "\t\t * if wake tcs was re-purposed for sending active\n"
        "\t\t * votes, clear AMC trigger & enable modes and\n"
        "\t\t * disable interrupt for this TCS\n"
        "\t\t */\n"
        "\t\tif (!drv->tcs[ACTIVE_TCS].num_tcs) {\n"
        "\t\t\t__tcs_trigger(drv, i, false);\n"
        "\t\t\t/*\n"
        "\t\t\t * Disable interrupt for this TCS to avoid being\n"
        "\t\t\t * spammed with interrupts coming when the solver\n"
        "\t\t\t * sends its wake votes.\n"
        "\t\t\t */\n"
        "\t\t\tenable_tcs_irq(drv, i, false);\n"
        "\t\t}\n"
    )
    endpoint = (
        "\t\t/*\n"
        "\t\t * Clear AMC trigger & enable modes for this TCS. If wake TCS\n"
        "\t\t * was re-purposed for active votes, also disable its IRQ.\n"
        "\t\t */\n"
        "\t\t__tcs_trigger(drv, i, false);\n"
        "\t\tif (!drv->tcs[ACTIVE_TCS].num_tcs) {\n"
        "\t\t\t/*\n"
        "\t\t\t * Disable interrupt for this TCS to avoid being\n"
        "\t\t\t * spammed with interrupts coming when the solver\n"
        "\t\t\t * sends its wake votes.\n"
        "\t\t\t */\n"
        "\t\t\tenable_tcs_irq(drv, i, false);\n"
        "\t\t}\n"
    )

    if endpoint not in s:
        if old not in s:
            raise RuntimeError(
                "Direct-302 rpmh-rsc: neither frozen Lisa nor reviewed 5.4.302 endpoint block found"
            )
        s = once(s, old, endpoint, "Direct-302 rpmh-rsc completed-TCS trigger cleanup")

    if s.count("\t\t__tcs_trigger(drv, i, false);\n") != 1:
        raise RuntimeError("Direct-302 rpmh-rsc: expected exactly one completed-TCS trigger clear")
    if endpoint not in s:
        raise RuntimeError("Direct-302 rpmh-rsc: reviewed endpoint not materialized")

    p.write_text(s)


def adapt_usb_core_quirks(root: Path):
    p = root / "drivers/usb/core/quirks.c"
    s = p.read_text()

    lisa_silicon = (
        "\t/* Silicon Motion Flash drive */\n"
        "\t{ USB_DEVICE(0x090c, 0x1000), .driver_info = USB_QUIRK_NO_LPM },\n"
    )
    endpoint_silicon = (
        "\t/* Silicon Motion Flash Drive */\n"
        "\t{ USB_DEVICE(0x090c, 0x1000), .driver_info =\n"
        "\t\t\tUSB_QUIRK_DELAY_INIT | USB_QUIRK_NO_LPM },\n"
    )

    if endpoint_silicon not in s:
        if lisa_silicon not in s:
            raise RuntimeError(
                "Direct-302 usb quirks: Silicon Motion Lisa downstream endpoint not found"
            )
        s = once(
            s,
            lisa_silicon,
            endpoint_silicon,
            "Direct-302 USB Silicon Motion combined delay-init + NO_LPM",
        )

    required = (
        "USB_DEVICE(0x046d, 0x0825), .driver_info = USB_QUIRK_RESET_RESUME |",
        "USB_DEVICE(0x067b, 0x2731), .driver_info = USB_QUIRK_DELAY_INIT |",
        "USB_DEVICE(0x0781, 0x5596), .driver_info = USB_QUIRK_DELAY_INIT",
        "USB_DEVICE(0x0781, 0x55a3), .driver_info = USB_QUIRK_DELAY_INIT",
        "USB_DEVICE(0x0781, 0x55ae), .driver_info = USB_QUIRK_NO_LPM",
        "USB_DEVICE(0x0fce, 0x0dde), .driver_info = USB_QUIRK_NO_LPM",
        "USB_DEVICE(0x12d1, 0x15c1), .driver_info =",
        "USB_DEVICE(0x1f75, 0x0917), .driver_info = USB_QUIRK_NO_LPM",
        "USB_DEVICE(0x2109, 0x0711), .driver_info = USB_QUIRK_NO_LPM",
        'dev_dbg(&udev->dev, "USB quirks for this device: 0x%x\\n",',
    )
    for token in required:
        if token not in s:
            raise RuntimeError(f"Direct-302 usb quirks endpoint missing: {token}")

    if s.count("USB_DEVICE(0x090c, 0x1000)") != 1:
        raise RuntimeError("Direct-302 usb quirks: expected exactly one Silicon Motion device entry")
    if "USB_QUIRK_DELAY_INIT | USB_QUIRK_NO_LPM" not in s:
        raise RuntimeError("Direct-302 usb quirks: Silicon Motion combined flags missing")

    p.write_text(s)


def adapt_dwc3_qcom(root: Path):
    p = root / "drivers/usb/dwc3/dwc3-qcom.c"
    s = p.read_text()

    # Segment C 5.4.296->5.4.299 stable endpoint ("usb: dwc3: qcom:
    # Don't leave BCR asserted"). The one-shot patch may already have applied
    # the direct-return and remove() hunks cleanly; make the adapter idempotent
    # and only remove the stale reset_assert error tail when it remains.
    s = s.replace(
        "\t\tdev_err(&pdev->dev, \"failed to deassert resets, err=%d\\n\", ret);\n"
        "\t\tgoto reset_assert;\n",
        "\t\tdev_err(&pdev->dev, \"failed to deassert resets, err=%d\\n\", ret);\n"
        "\t\treturn ret;\n",
    )
    s = s.replace(
        "\t\tdev_err(dev, \"failed to get clocks\\n\");\n"
        "\t\tgoto reset_assert;\n",
        "\t\tdev_err(dev, \"failed to get clocks\\n\");\n"
        "\t\treturn ret;\n",
    )

    stale_tail = (
        "reset_assert:\n"
        "\treset_control_assert(qcom->resets);\n\n"
        "\treturn ret;\n"
    )
    if stale_tail in s:
        s = s.replace(stale_tail, "\treturn ret;\n", 1)

    # Remove-time BCR assertion was part of the same stable fix. Restrict the
    # edit to dwc3_qcom_remove() so the required initial probe assertion stays.
    remove_start = s.find("static int dwc3_qcom_remove(struct platform_device *pdev)")
    if remove_start < 0:
        raise RuntimeError("Direct-302 dwc3-qcom: remove function missing")
    remove_end = s.find("\nstatic ", remove_start + 1)
    if remove_end < 0:
        remove_end = len(s)
    remove_body = s[remove_start:remove_end]
    remove_body = remove_body.replace(
        "\n\treset_control_assert(qcom->resets);\n",
        "\n",
    )
    s = s[:remove_start] + remove_body + s[remove_end:]

    # Final endpoint assertions. Keep the one initial probe assertion, but no
    # stale reset_assert label/gotos and no remove-time BCR assertion.
    if "goto reset_assert;" in s or "\nreset_assert:\n" in s:
        raise RuntimeError("Direct-302 dwc3-qcom: stale reset_assert path remains")

    deassert_block = (
        "\tret = reset_control_deassert(qcom->resets);\n"
        "\tif (ret) {\n"
        "\t\tdev_err(&pdev->dev, \"failed to deassert resets, err=%d\\n\", ret);\n"
        "\t\treturn ret;\n"
        "\t}\n"
    )
    if deassert_block not in s:
        raise RuntimeError("Direct-302 dwc3-qcom: deassert failure is not direct-return endpoint")

    clk_block = (
        "\tret = dwc3_qcom_clk_init(qcom, of_clk_get_parent_count(np));\n"
        "\tif (ret) {\n"
        "\t\tdev_err(dev, \"failed to get clocks\\n\");\n"
        "\t\treturn ret;\n"
        "\t}\n"
    )
    if clk_block not in s:
        raise RuntimeError("Direct-302 dwc3-qcom: clock-init failure is not direct-return endpoint")

    remove_body = s[remove_start:s.find("\nstatic ", remove_start + 1)]
    if "reset_control_assert(qcom->resets);" in remove_body:
        raise RuntimeError("Direct-302 dwc3-qcom: remove-time BCR assertion remains")

    # Lisa-specific downstream integration must survive the stable endpoint
    # adaptation; do not replace the file wholesale with upstream.
    for token in ("USB3_GDSC", "qcom->clks", "qcom->num_clocks"):
        if token not in s:
            raise RuntimeError(f"Direct-302 dwc3-qcom: lost Lisa downstream token {token}")

    p.write_text(s)



def adapt_dwc3_gadget(root: Path):
    p = root / "drivers/usb/dwc3/gadget.c"
    s = p.read_text()

    # Segment A endpoint: keep Lisa downstream controller/GSI flow while
    # applying the reviewed stable run/stop timing and USB2 PHY save/restore.
    if "\tu32\t\t\ttimeout = 2000;\n" not in s:
        s = once(
            s,
            "\tu32\t\t\ttimeout = 1500;\n",
            "\tu32\t\t\ttimeout = 2000;\n\tu32\t\t\tsaved_config = 0;\n",
            "Direct-302 dwc3 gadget timeout",
        )
    elif "\tu32\t\t\tsaved_config = 0;\n" not in s:
        s = once(
            s,
            "\tu32\t\t\ttimeout = 2000;\n",
            "\tu32\t\t\ttimeout = 2000;\n\tu32\t\t\tsaved_config = 0;\n",
            "Direct-302 dwc3 gadget saved_config",
        )

    phy_add = (
        "\treg = dwc3_readl(dwc->regs, DWC3_GUSB2PHYCFG(0));\n"
        "\tif (reg & DWC3_GUSB2PHYCFG_SUSPHY) {\n"
        "\t\tsaved_config |= DWC3_GUSB2PHYCFG_SUSPHY;\n"
        "\t\treg &= ~DWC3_GUSB2PHYCFG_SUSPHY;\n"
        "\t}\n"
        "\tif (reg & DWC3_GUSB2PHYCFG_ENBLSLPM) {\n"
        "\t\tsaved_config |= DWC3_GUSB2PHYCFG_ENBLSLPM;\n"
        "\t\treg &= ~DWC3_GUSB2PHYCFG_ENBLSLPM;\n"
        "\t}\n"
        "\tif (saved_config)\n"
        "\t\tdwc3_writel(dwc->regs, DWC3_GUSB2PHYCFG(0), reg);\n\n"
    )
    if phy_add not in s:
        anchor = '\tdbg_event(0xFF, "run_stop", is_on);\n'
        s = once(s, anchor, anchor + phy_add, "Direct-302 dwc3 gadget PHY save")

    if "\t\tusleep_range(1000, 2000);\n" not in s:
        old = (
            "\tdo {\n"
            "\t\treg = dwc3_readl(dwc->regs, DWC3_DSTS);\n"
            "\t\treg &= DWC3_DSTS_DEVCTRLHLT;\n"
            "\t} while (--timeout && !(!is_on ^ !reg));\n\n"
            "\tif (!timeout) {"
        )
        new = (
            "\tdo {\n"
            "\t\tusleep_range(1000, 2000);\n"
            "\t\treg = dwc3_readl(dwc->regs, DWC3_DSTS);\n"
            "\t\treg &= DWC3_DSTS_DEVCTRLHLT;\n"
            "\t} while (--timeout && !(!is_on ^ !reg));\n\n"
            "\tif (saved_config) {\n"
            "\t\treg = dwc3_readl(dwc->regs, DWC3_GUSB2PHYCFG(0));\n"
            "\t\treg |= saved_config;\n"
            "\t\tdwc3_writel(dwc->regs, DWC3_GUSB2PHYCFG(0), reg);\n"
            "\t}\n\n"
            "\tif (!timeout) {"
        )
        s = once(s, old, new, "Direct-302 dwc3 gadget runstop poll")
    elif "\t\treg |= saved_config;\n" not in s:
        anchor = "\t} while (--timeout && !(!is_on ^ !reg));\n\n"
        restore = (
            "\tif (saved_config) {\n"
            "\t\treg = dwc3_readl(dwc->regs, DWC3_GUSB2PHYCFG(0));\n"
            "\t\treg |= saved_config;\n"
            "\t\tdwc3_writel(dwc->regs, DWC3_GUSB2PHYCFG(0), reg);\n"
            "\t}\n\n"
        )
        s = once(s, anchor, anchor + restore, "Direct-302 dwc3 gadget PHY restore")

    # Segment B endpoint: reject a corrupt event count larger than the buffer.
    count_guard = (
        "\tif (count > evt->length) {\n"
        "\t\tdev_err_ratelimited(dwc->dev, \"invalid count(%u) > evt->length(%u)\\n\",\n"
        "\t\t\tcount, evt->length);\n"
        "\t\treturn IRQ_NONE;\n"
        "\t}\n\n"
    )
    if count_guard not in s:
        anchor = (
            "\tcount = dwc3_readl(dwc->regs, DWC3_GEVNTCOUNT(0));\n"
            "\tcount &= DWC3_GEVNTCOUNT_MASK;\n"
            "\tif (!count)\n"
            "\t\treturn IRQ_NONE;\n\n"
        )
        s = once(s, anchor, anchor + count_guard, "Direct-302 dwc3 gadget event count guard")

    # Segment C endpoint: ignore a late XferNotReady after device-initiated
    # disconnect so no new transfer can start while the controller is halting.
    xfer_guard = (
        "\t/*\n"
        "\t * During a device-initiated disconnect, a late xferNotReady event can\n"
        "\t * be generated after the End Transfer command resets the event filter,\n"
        "\t * but before the controller is halted. Ignore it to prevent a new\n"
        "\t * transfer from starting.\n"
        "\t */\n"
        "\tif (!dep->dwc->connected)\n"
        "\t\treturn;\n\n"
    )
    if xfer_guard not in s:
        anchor = (
            "static void dwc3_gadget_endpoint_transfer_not_ready(struct dwc3_ep *dep,\n"
            "\t\tconst struct dwc3_event_depevt *event)\n"
            "{\n"
        )
        s = once(s, anchor, anchor + xfer_guard, "Direct-302 dwc3 gadget late XferNotReady guard")

    for token in (
        "timeout = 2000",
        "saved_config = 0",
        "usleep_range(1000, 2000)",
        "count > evt->length",
        "if (!dep->dwc->connected)",
    ):
        if token not in s:
            raise RuntimeError(f"Direct-302 dwc3 gadget endpoint missing {token}")

    # Preserve Lisa downstream functionality; this is an endpoint adaptation,
    # never an upstream whole-file replacement.
    for token in ("dbg_event", "DWC3_DCTL_RUN_STOP", "dwc3_gadget_run_stop"):
        if token not in s:
            raise RuntimeError(f"Direct-302 dwc3 gadget lost Lisa/downstream token {token}")

    p.write_text(s)



def adapt_functionfs(root: Path):
    p = root / "drivers/usb/gadget/function/f_fs.c"
    s = p.read_text()

    # Segment A: do not WARN on a userspace-visible bind-state race. Preserve
    # Lisa/Xiaomi ffs_log instrumentation around the stable condition.
    s = s.replace(
        "\tif (WARN_ON(ffs->state != FFS_ACTIVE\n"
        "\t\t || test_and_set_bit(FFS_FL_BOUND, &ffs->flags)))\n",
        "\tif ((ffs->state != FFS_ACTIVE\n"
        "\t\t || test_and_set_bit(FFS_FL_BOUND, &ffs->flags)))\n",
        1,
    )

    if "WARN_ON(ffs->state != FFS_ACTIVE" in s:
        raise RuntimeError("Direct-302 FunctionFS still WARNs on bind state")

    bind_endpoint = (
        "\tif ((ffs->state != FFS_ACTIVE\n"
        "\t\t || test_and_set_bit(FFS_FL_BOUND, &ffs->flags)))\n"
        "\t\treturn -EBADFD;\n"
    )
    if bind_endpoint not in s:
        raise RuntimeError("Direct-302 FunctionFS Segment-A bind endpoint missing")

    # Segment D: reject endpoint enable when epfiles allocation is absent.
    # git apply may already have applied this hunk before the Segment-A reject,
    # so make the endpoint adaptation idempotent.
    ep_guard = (
        "\tif (!epfile) {\n"
        "\t\tret = -ENOMEM;\n"
        "\t\tgoto done;\n"
        "\t}\n\n"
    )
    if ep_guard not in s:
        anchor = (
            "\tepfile = ffs->epfiles;\n"
            "\tcount = ffs->eps_count;\n"
        )
        s = once(
            s,
            anchor,
            anchor + ep_guard,
            "Direct-302 FunctionFS epfiles null guard",
        )

    s = s.replace("\twhile(count--) {\n", "\twhile (count--) {\n", 1)

    done_anchor = "\twake_up_interruptible(&ffs->wait);\n"
    done_endpoint = "\twake_up_interruptible(&ffs->wait);\ndone:\n"
    if done_endpoint not in s:
        s = once(
            s,
            done_anchor,
            done_endpoint,
            "Direct-302 FunctionFS done label",
        )

    for token in (
        "if (!epfile)",
        "goto done;",
        "while (count--)",
        "wake_up_interruptible(&ffs->wait);\ndone:",
    ):
        if token not in s:
            raise RuntimeError(f"Direct-302 FunctionFS endpoint missing {token}")

    # Preserve Lisa downstream debug instrumentation rather than replacing the
    # whole file with upstream.
    for token in ("ffs_log(", "setup_state", "FFS_FL_BOUND"):
        if token not in s:
            raise RuntimeError(f"Direct-302 FunctionFS lost Lisa token {token}")

    p.write_text(s)



def adapt_function_ncm(root: Path):
    p = root / "drivers/usb/gadget/function/f_ncm.c"
    s = p.read_text()

    # Segment D 5.4.299->5.4.302 moves the shared MAC string pointer from
    # allocation time to bind time. MiYume 5.4.302 confirms the same endpoint
    # on top of Xiaomi's downstream gether_setup_default()/bind-time address
    # generation flow. Preserve that downstream flow; only move the assignment.
    alloc_line = "\tncm_string_defs[STRING_MAC_IDX].s = ncm->ethaddr;\n"
    if alloc_line in s:
        s = s.replace(alloc_line, "", 1)

    bind_endpoint = (
        "\tncm->port.ioport = netdev_priv(ncm_opts->net);\n\n"
        "\tncm_string_defs[STRING_MAC_IDX].s = ncm->ethaddr;\n\n"
        "\tus = usb_gstrings_attach(cdev, ncm_strings,\n"
    )
    if bind_endpoint not in s:
        anchor = (
            "\tncm->port.ioport = netdev_priv(ncm_opts->net);\n\n"
            "\tus = usb_gstrings_attach(cdev, ncm_strings,\n"
        )
        replacement = (
            "\tncm->port.ioport = netdev_priv(ncm_opts->net);\n\n"
            "\tncm_string_defs[STRING_MAC_IDX].s = ncm->ethaddr;\n\n"
            "\tus = usb_gstrings_attach(cdev, ncm_strings,\n"
        )
        s = once(
            s,
            anchor,
            replacement,
            "Direct-302 NCM bind-time MAC string endpoint",
        )

    if s.count("ncm_string_defs[STRING_MAC_IDX].s = ncm->ethaddr;") != 1:
        raise RuntimeError(
            "Direct-302 NCM expected exactly one bind-time MAC string assignment"
        )

    bind_start = s.find("static int ncm_bind(")
    alloc_start = s.find("static struct usb_function *ncm_alloc(")
    if bind_start < 0 or alloc_start < 0:
        raise RuntimeError("Direct-302 NCM bind/alloc function missing")
    bind_body = s[bind_start:alloc_start]
    alloc_body = s[alloc_start:]

    if "ncm_string_defs[STRING_MAC_IDX].s = ncm->ethaddr;" not in bind_body:
        raise RuntimeError("Direct-302 NCM bind-time MAC assignment missing")
    if "ncm_string_defs[STRING_MAC_IDX].s = ncm->ethaddr;" in alloc_body:
        raise RuntimeError("Direct-302 NCM stale alloc-time MAC assignment remains")

    # Preserve Lisa/Xiaomi downstream lifecycle rather than replacing the file
    # wholesale with upstream.
    for token in (
        "gether_setup_default()",
        "gether_register_netdev",
        "gether_get_host_addr_cdc(ncm_opts->net, ncm->ethaddr",
        "ncm->port.ioport = netdev_priv(ncm_opts->net)",
    ):
        if token not in s:
            raise RuntimeError(f"Direct-302 NCM lost Lisa downstream token {token}")

    p.write_text(s)



def adapt_xhci_plat(root: Path):
    p = root / "drivers/usb/host/xhci-plat.c"
    s = p.read_text()

    # Segment C 5.4.296->5.4.299: do not advertise streams when the controller
    # carries XHCI_BROKEN_STREAMS.
    old_streams = (
        "\tif (HCC_MAX_PSA(xhci->hcc_params) >= 4)\n"
        "\t\txhci->shared_hcd->can_do_streams = 1;\n"
    )
    endpoint_streams = (
        "\tif (HCC_MAX_PSA(xhci->hcc_params) >= 4 &&\n"
        "\t    !(xhci->quirks & XHCI_BROKEN_STREAMS))\n"
        "\t\txhci->shared_hcd->can_do_streams = 1;\n"
    )
    if endpoint_streams not in s:
        s = once(
            s,
            old_streams,
            endpoint_streams,
            "Direct-302 xhci broken-streams guard",
        )

    # Segment D 5.4.299->5.4.302 adds runtime autosuspend use. Lisa/Xiaomi
    # already carries the stronger downstream endpoint with autosuspend enabled
    # plus a 1000 ms delay before set_active(). Preserve that ordering instead
    # of duplicating/reordering it to upstream.
    if s.count("pm_runtime_use_autosuspend(&pdev->dev);") != 1:
        raise RuntimeError(
            "Direct-302 xhci expected exactly one runtime autosuspend enable"
        )
    if "pm_runtime_set_autosuspend_delay(&pdev->dev, 1000);" not in s:
        raise RuntimeError(
            "Direct-302 xhci lost Lisa/Xiaomi 1000ms autosuspend delay"
        )
    if s.index("pm_runtime_use_autosuspend(&pdev->dev);") > s.index("pm_runtime_set_active(&pdev->dev);"):
        raise RuntimeError(
            "Direct-302 xhci Lisa/MiYume autosuspend ordering changed"
        )

    if endpoint_streams not in s:
        raise RuntimeError("Direct-302 xhci broken-streams endpoint missing")

    # Preserve the Lisa/Xiaomi runtime-PM/wakeup flow rather than replacing the
    # whole file with upstream.
    for token in (
        "pm_runtime_get_sync(&pdev->dev)",
        "pm_runtime_mark_last_busy(&pdev->dev)",
        "pm_runtime_put_autosuspend(&pdev->dev)",
        "device_wakeup_enable(&xhci->shared_hcd->self.root_hub->dev)",
    ):
        if token not in s:
            raise RuntimeError(f"Direct-302 xhci lost Lisa downstream token {token}")

    p.write_text(s)



def adapt_ext4_dir(root: Path):
    p = root / "fs/ext4/dir.c"
    s = p.read_text()

    # Lisa/Xiaomi already carries a stronger downstream directory-entry
    # validator: next_offset bounds, fake-dir awareness, metadata-csum-aware
    # ext4_dir_rec_len(), and fake-entry diagnostics. Segment B only needs the
    # stable endpoint which rejects "." as the final entry of a data block.
    dot_guard = (
        "\telse if (unlikely(next_offset == size && de->name_len == 1 &&\n"
        "\t\t\t  de->name[0] == '.'))\n"
        "\t\terror_msg = \"'.' directory cannot be the last in data block\";\n"
    )
    if dot_guard not in s:
        anchor = (
            "\telse if (unlikely(le32_to_cpu(de->inode) >\n"
            "\t\t\tle32_to_cpu(EXT4_SB(dir->i_sb)->s_es->s_inodes_count)))\n"
            "\t\terror_msg = \"inode out of bounds\";\n"
        )
        s = once(
            s,
            anchor,
            anchor + dot_guard,
            "Direct-302 ext4 final-dot directory entry guard",
        )

    for token in (
        "const int next_offset = ((char *) de - buf) + rlen;",
        "bool fake = is_fake_dir_entry(de);",
        "bool has_csum = ext4_has_metadata_csum(dir->i_sb);",
        "ext4_dir_rec_len(1, fake ? NULL : dir)",
        "next_offset > size - ext4_dir_rec_len(1,",
        "'.' directory cannot be the last in data block",
    ):
        if token not in s:
            raise RuntimeError(f"Direct-302 ext4 endpoint missing {token}")

    if s.count("'.' directory cannot be the last in data block") != 1:
        raise RuntimeError("Direct-302 ext4 final-dot guard count is not exactly one")

    p.write_text(s)



def adapt_pid_h(root: Path):
    p = root / "include/linux/pid.h"
    s = p.read_text()

    # Segment B 5.4.292->5.4.296 adds pidfd_prepare() and pid_has_task().
    # Preserve Lisa/MiYume's downstream pidfd_get_pid() declaration.
    prepare = "int pidfd_prepare(struct pid *pid, unsigned int flags, struct file **ret);\n"
    if prepare not in s:
        anchor = "extern struct pid *pidfd_pid(const struct file *file);\n"
        s = once(
            s,
            anchor,
            anchor + prepare,
            "Direct-302 pidfd_prepare declaration",
        )

    helper = (
        "static inline bool pid_has_task(struct pid *pid, enum pid_type type)\n"
        "{\n"
        "\treturn !hlist_empty(&pid->tasks[type]);\n"
        "}\n"
    )
    if helper not in s:
        anchor = "extern struct task_struct *pid_task(struct pid *pid, enum pid_type);\n"
        s = once(
            s,
            anchor,
            anchor + helper,
            "Direct-302 pid_has_task helper",
        )

    for token in (
        "int pidfd_prepare(struct pid *pid, unsigned int flags, struct file **ret);",
        "struct pid *pidfd_get_pid(unsigned int fd);",
        "static inline bool pid_has_task(struct pid *pid, enum pid_type type)",
        "return !hlist_empty(&pid->tasks[type]);",
    ):
        if token not in s:
            raise RuntimeError(f"Direct-302 pid.h endpoint missing {token}")

    if s.count("pidfd_prepare(struct pid *pid") != 1:
        raise RuntimeError("Direct-302 pid.h pidfd_prepare count is not exactly one")
    if s.count("static inline bool pid_has_task(") != 1:
        raise RuntimeError("Direct-302 pid.h pid_has_task count is not exactly one")

    p.write_text(s)


def adapt_usbnet_h(root: Path):
    p = root / "include/linux/usb/usbnet.h"
    s = p.read_text()
    token = "#\t\tdefine EVENT_LINK_CARRIER_ON\t14\n"
    if token not in s:
        anchor = "#\t\tdefine EVENT_NO_IP_ALIGN\t13\n"
        s = once(s, anchor, anchor + token, "Direct-302 usbnet carrier event")
    if "ANDROID_KABI_USE2(1, u32 rx_speed, u32 tx_speed);" not in s:
        raise RuntimeError("Direct-302 usbnet Android KABI layout missing")
    if s.count("EVENT_LINK_CARRIER_ON") != 1:
        raise RuntimeError("Direct-302 usbnet carrier event count invalid")
    p.write_text(s)



def adapt_net_sock_h(root: Path):
    p = root / "include/net/sock.h"
    s = p.read_text()

    # Segment D stable backport 83083c5f holds the module which owns a
    # socket-specific lockdep class until the socket is actually freed.
    # MiYume 5.4.302 carries the same endpoint on top of the Android KABI
    # layout. Preserve all Lisa KABI reserve/vendor slots.
    doc = (
        "  *\t@sk_owner: reference to the real owner of the socket that calls\n"
        "  *\t\t   sock_lock_init_class_and_name().\n"
    )
    if doc not in s:
        anchor = "  *\t@sk_txtime_unused: unused txtime flags\n"
        s = once(s, anchor, anchor + doc, "Direct-302 sock owner documentation")

    owner_field = (
        "#if IS_ENABLED(CONFIG_PROVE_LOCKING) && IS_ENABLED(CONFIG_MODULES)\n"
        "\tstruct module\t\t*sk_owner;\n"
        "#endif\n\n"
    )
    if owner_field not in s:
        anchor = "\tstruct rcu_head\t\tsk_rcu;\n\n"
        s = once(s, anchor, anchor + owner_field, "Direct-302 sock owner field")

    owner_helpers = (
        "#if IS_ENABLED(CONFIG_PROVE_LOCKING) && IS_ENABLED(CONFIG_MODULES)\n"
        "static inline void sk_owner_set(struct sock *sk, struct module *owner)\n"
        "{\n"
        "\t__module_get(owner);\n"
        "\tsk->sk_owner = owner;\n"
        "}\n\n"
        "static inline void sk_owner_clear(struct sock *sk)\n"
        "{\n"
        "\tsk->sk_owner = NULL;\n"
        "}\n\n"
        "static inline void sk_owner_put(struct sock *sk)\n"
        "{\n"
        "\tmodule_put(sk->sk_owner);\n"
        "}\n"
        "#else\n"
        "static inline void sk_owner_set(struct sock *sk, struct module *owner)\n"
        "{\n"
        "}\n\n"
        "static inline void sk_owner_clear(struct sock *sk)\n"
        "{\n"
        "}\n\n"
        "static inline void sk_owner_put(struct sock *sk)\n"
        "{\n"
        "}\n"
        "#endif\n\n"
    )
    if "static inline void sk_owner_set(" not in s:
        anchor = (
            "static inline void sock_release_ownership(struct sock *sk)\n"
            "{\n"
            "\tif (sk->sk_lock.owned) {\n"
            "\t\tsk->sk_lock.owned = 0;\n\n"
            "\t\t/* The sk_lock has mutex_unlock() semantics: */\n"
            "\t\tmutex_release(&sk->sk_lock.dep_map, 1, _RET_IP_);\n"
            "\t}\n"
            "}\n\n"
        )
        s = once(
            s,
            anchor,
            anchor + owner_helpers,
            "Direct-302 sock owner helper functions",
        )

    macro_head = (
        "#define sock_lock_init_class_and_name(sk, sname, skey, name, key)\t\\\n"
        "do {\t\t\t\t\t\t\t\t\t\\\n"
    )
    macro_endpoint = macro_head + "\tsk_owner_set(sk, THIS_MODULE);\t\t\t\t\t\\\n"
    if macro_endpoint not in s:
        s = once(
            s,
            macro_head,
            macro_endpoint,
            "Direct-302 sock lock owner acquisition",
        )

    for token in (
        "struct module\t\t*sk_owner;",
        "static inline void sk_owner_set(",
        "static inline void sk_owner_clear(",
        "static inline void sk_owner_put(",
        "sk_owner_set(sk, THIS_MODULE);",
        "ANDROID_KABI_RESERVE(1);",
        "ANDROID_KABI_RESERVE(8);",
        "ANDROID_VENDOR_DATA(1);",
    ):
        if token not in s:
            raise RuntimeError(f"Direct-302 sock.h endpoint missing {token}")

    if s.count("sk_owner_set(sk, THIS_MODULE);") != 1:
        raise RuntimeError("Direct-302 sock.h owner acquisition count invalid")

    p.write_text(s)



def adapt_sched_fair(root: Path):
    p = root / "kernel/sched/fair.c"
    s = p.read_text()

    # Segment D stable chain:
    #   d8dd0400 / 7335a5a0 / ca51183e / d0936c8b
    # finalizes newidle_balance() as static sched_balance_newidle() and makes
    # lost-idle PELT accounting run even when pick_next_task_fair() has no
    # rq_flags pointer. Preserve all Lisa WALT/force_lb/prefer_spread logic.
    decl = "static int sched_balance_newidle(struct rq *this_rq, struct rq_flags *rf);\n\n"
    if decl not in s:
        anchor = (
            "static inline unsigned long cfs_rq_load_avg(struct cfs_rq *cfs_rq)\n"
            "{\n"
            "\treturn cfs_rq->avg.load_avg;\n"
            "}\n\n"
        )
        s = once(
            s,
            anchor,
            anchor + decl,
            "Direct-302 fair sched_balance_newidle declaration",
        )

    # Rename only the standalone scheduler helper references; do not touch
    # nohz_newidle_balance().
    replacements = (
        ("return newidle_balance(rq, rf) != 0;",
         "return sched_balance_newidle(rq, rf) != 0;"),
        ("newidle_balance() disregards balance intervals",
         "sched_balance_newidle() disregards balance intervals"),
        (" * idle_balance is called by schedule() if this_cpu is about to become\n",
         " * sched_balance_newidle is called by schedule() if this_cpu is about to become\n"),
        ("int newidle_balance(struct rq *this_rq, struct rq_flags *rf)\n",
         "static int sched_balance_newidle(struct rq *this_rq, struct rq_flags *rf)\n"),
    )
    for old, new in replacements:
        if old in s:
            s = s.replace(old, new, 1)

    old_idle = (
        "idle:\n"
        "\tif (!rf)\n"
        "\t\treturn NULL;\n\n"
        "\tnew_tasks = newidle_balance(rq, rf);\n\n"
        "\t/*\n"
        "\t * Because newidle_balance() releases (and re-acquires) rq->lock, it is\n"
        "\t * possible for any higher priority task to appear. In that case we\n"
        "\t * must re-start the pick_next_entity() loop.\n"
        "\t */\n"
        "\tif (new_tasks < 0)\n"
        "\t\treturn RETRY_TASK;\n\n"
        "\tif (new_tasks > 0)\n"
        "\t\tgoto again;\n"
    )
    new_idle = (
        "idle:\n"
        "\tif (rf) {\n"
        "\t\tnew_tasks = sched_balance_newidle(rq, rf);\n\n"
        "\t\t/*\n"
        "\t\t * Because sched_balance_newidle() releases (and re-acquires)\n"
        "\t\t * rq->lock, it is possible for any higher priority task to\n"
        "\t\t * appear. In that case we must re-start the pick_next_entity()\n"
        "\t\t * loop.\n"
        "\t\t */\n"
        "\t\tif (new_tasks < 0)\n"
        "\t\t\treturn RETRY_TASK;\n\n"
        "\t\tif (new_tasks > 0)\n"
        "\t\t\tgoto again;\n"
        "\t}\n"
    )
    if new_idle not in s:
        s = once(
            s,
            old_idle,
            new_idle,
            "Direct-302 fair lost-idle PELT endpoint",
        )

    for token in (
        "static int sched_balance_newidle(struct rq *this_rq, struct rq_flags *rf);",
        "return sched_balance_newidle(rq, rf) != 0;",
        "new_tasks = sched_balance_newidle(rq, rf);",
        "Because sched_balance_newidle() releases",
        "sched_balance_newidle() disregards balance intervals",
        "static int sched_balance_newidle(struct rq *this_rq, struct rq_flags *rf)\n{",
        "update_idle_rq_clock_pelt(rq);",
        "bool prefer_spread = prefer_spread_on_idle(this_cpu, true);",
        "sysctl_sched_force_lb_enable",
        "nohz_newidle_balance(this_rq);",
    ):
        if token not in s:
            raise RuntimeError(f"Direct-302 fair endpoint missing {token}")

    for stale in (
        "return newidle_balance(rq, rf) != 0;",
        "new_tasks = newidle_balance(rq, rf);",
        "Because newidle_balance() releases",
        "newidle_balance() disregards balance intervals",
        "int newidle_balance(struct rq *this_rq, struct rq_flags *rf)\n{",
    ):
        if stale in s:
            raise RuntimeError(f"Direct-302 fair stale endpoint remains {stale}")

    p.write_text(s)



def adapt_softirq(root: Path):
    p = root / "kernel/softirq.c"
    s = p.read_text()

    # Segment A tasklet callback compatibility. In the Direct-302 materializer
    # the setup/init hunk can apply cleanly before the Lisa trace-instrumented
    # dispatch hunk rejects, so this adapter must be idempotent.
    dispatch = (
        "\t\t\t\ttrace_tasklet_entry(t->func);\n"
        "\t\t\t\tif (t->use_callback)\n"
        "\t\t\t\t\tt->callback(t);\n"
        "\t\t\t\telse\n"
        "\t\t\t\t\tt->func(t->data);\n"
        "\t\t\t\ttrace_tasklet_exit(t->func);\n"
    )
    if dispatch not in s:
        old = (
            "\t\t\t\ttrace_tasklet_entry(t->func);\n"
            "\t\t\t\tt->func(t->data);\n"
            "\t\t\t\ttrace_tasklet_exit(t->func);\n"
        )
        s = once(
            s,
            old,
            dispatch,
            "Direct-302 tasklet callback dispatch",
        )

    setup = (
        "void tasklet_setup(struct tasklet_struct *t,\n"
        "\t\t   void (*callback)(struct tasklet_struct *))\n"
        "{\n"
        "\tt->next = NULL;\n"
        "\tt->state = 0;\n"
        "\tatomic_set(&t->count, 0);\n"
        "\tt->callback = callback;\n"
        "\tt->use_callback = true;\n"
        "\tt->data = 0;\n"
        "}\n"
        "EXPORT_SYMBOL(tasklet_setup);\n\n"
    )
    if "void tasklet_setup(struct tasklet_struct *t," not in s:
        anchor = "void tasklet_init(struct tasklet_struct *t,\n"
        s = once(
            s,
            anchor,
            setup + anchor,
            "Direct-302 tasklet setup endpoint",
        )

    init_endpoint = (
        "\tt->func = func;\n"
        "\tt->use_callback = false;\n"
        "\tt->data = data;\n"
    )
    if init_endpoint not in s:
        old = (
            "\tt->func = func;\n"
            "\tt->data = data;\n"
        )
        s = once(
            s,
            old,
            init_endpoint,
            "Direct-302 tasklet init callback mode",
        )

    for token in (
        "if (t->use_callback)",
        "t->callback(t);",
        "void tasklet_setup(struct tasklet_struct *t,",
        "t->callback = callback;",
        "t->use_callback = true;",
        "t->use_callback = false;",
        "trace_tasklet_entry(t->func);",
        "trace_tasklet_exit(t->func);",
    ):
        if token not in s:
            raise RuntimeError(f"Direct-302 softirq endpoint missing {token}")

    if s.count("void tasklet_setup(struct tasklet_struct *t,") != 1:
        raise RuntimeError("Direct-302 softirq tasklet_setup count invalid")
    if s.count("t->use_callback = false;") != 1:
        raise RuntimeError("Direct-302 softirq legacy init mode count invalid")

    p.write_text(s)



def adapt_posix_timers(root: Path):
    p = root / "kernel/time/posix-timers.c"
    s = p.read_text()

    # Segment B adds a reschedule point to the timer-ID collision retry loop.
    # Lisa retains the older posix_timer_id do/while allocator rather than the
    # upstream next_posix_timer_id for-loop, so preserve that downstream ABI/
    # CRIU-visible allocation scheme and add only the retry reschedule semantic.
    func_start = s.find("static int posix_timer_add(struct k_itimer *timer)")
    func_end = s.find("static inline void unlock_timer", func_start)
    if func_start < 0 or func_end < 0:
        raise RuntimeError("Direct-302 posix timer allocator boundaries missing")

    body = s[func_start:func_end]
    if "cond_resched();" not in body:
        lisa_anchor = (
            "\t\tspin_unlock(&hash_lock);\n"
            "\t} while (ret == -ENOENT);\n"
        )
        lisa_endpoint = (
            "\t\tspin_unlock(&hash_lock);\n"
            "\t\tif (ret == -ENOENT)\n"
            "\t\t\tcond_resched();\n"
            "\t} while (ret == -ENOENT);\n"
        )
        if lisa_anchor in body:
            body = body.replace(lisa_anchor, lisa_endpoint, 1)
        else:
            upstream_anchor = (
                "\t\tspin_unlock(&hash_lock);\n"
                "\t}\n"
                "\t/* POSIX return code when no timer ID could be allocated */\n"
            )
            upstream_endpoint = (
                "\t\tspin_unlock(&hash_lock);\n"
                "\t\tcond_resched();\n"
                "\t}\n"
                "\t/* POSIX return code when no timer ID could be allocated */\n"
            )
            if upstream_anchor not in body:
                raise RuntimeError("Direct-302 posix timer retry anchor missing")
            body = body.replace(upstream_anchor, upstream_endpoint, 1)
        s = s[:func_start] + body + s[func_end:]

    body = s[func_start:s.find("static inline void unlock_timer", func_start)]
    if "cond_resched();" not in body:
        raise RuntimeError("Direct-302 posix timer cond_resched endpoint missing")

    # Preserve whichever allocator layout Lisa carries; do not force the newer
    # upstream next_posix_timer_id field onto the downstream signal ABI.
    if "sig->posix_timer_id" in body:
        for token in (
            "int first_free_id = sig->posix_timer_id;",
            "} while (ret == -ENOENT);",
        ):
            if token not in body:
                raise RuntimeError(f"Direct-302 posix Lisa allocator lost {token}")

    p.write_text(s)



def adapt_oom_kill(root: Path):
    p = root / "mm/oom_kill.c"
    s = p.read_text()

    # Segment A endpoint is partially clean-applied by the one-shot delta on
    # some Lisa layouts. Make the Direct-302 adapter idempotent and preserve
    # downstream OOM structure rather than forcing the upstream whole file.
    if "#include <linux/cred.h>" not in s:
        anchor = "#include <linux/mmu_notifier.h>\n"
        s = once(
            s, anchor,
            anchor + "#include <linux/cred.h>\n#include <linux/nmi.h>\n",
            "Direct-302 oom includes",
        )
    elif "#include <linux/nmi.h>" not in s:
        anchor = "#include <linux/cred.h>\n"
        s = once(s, anchor, anchor + "#include <linux/nmi.h>\n",
                 "Direct-302 oom nmi include")

    # Stable endpoint: yield to the softlockup watchdog while dumping a very
    # large task list. If clean hunks already materialized it, leave intact.
    if "touch_softlockup_watchdog();" not in s:
        old = (
            "\telse {\n"
            "\t\tstruct task_struct *p;\n\n"
            "\t\trcu_read_lock();\n"
            "\t\tfor_each_process(p)\n"
            "\t\t\tdump_task(p, oc);\n"
            "\t\trcu_read_unlock();\n"
            "\t}"
        )
        new = (
            "\telse {\n"
            "\t\tstruct task_struct *p;\n"
            "\t\tint i = 0;\n\n"
            "\t\trcu_read_lock();\n"
            "\t\tfor_each_process(p) {\n"
            "\t\t\tif ((++i & 1023) == 0)\n"
            "\t\t\t\ttouch_softlockup_watchdog();\n"
            "\t\t\tdump_task(p, oc);\n"
            "\t\t}\n"
            "\t\trcu_read_unlock();\n"
            "\t}"
        )
        s = once(s, old, new, "Direct-302 oom dump watchdog")

    # Stable endpoint: trace the victim UID. Support both upstream-style and
    # Lisa downstream mark_oom_victim layouts, and tolerate clean application.
    if "const struct cred *cred;" not in s:
        upstream_anchor = (
            "static void mark_oom_victim(struct task_struct *tsk)\n"
            "{\n"
            "\tstruct mm_struct *mm = tsk->mm;"
        )
        lisa_anchor = (
            "static void mark_oom_victim(struct task_struct *tsk)\n"
            "{\n"
            "\tWARN_ON(oom_killer_disabled);"
        )
        if upstream_anchor in s:
            s = once(
                s, upstream_anchor,
                "static void mark_oom_victim(struct task_struct *tsk)\n"
                "{\n"
                "\tconst struct cred *cred;\n"
                "\tstruct mm_struct *mm = tsk->mm;",
                "Direct-302 oom cred upstream",
            )
        elif lisa_anchor in s:
            s = once(
                s, lisa_anchor,
                "static void mark_oom_victim(struct task_struct *tsk)\n"
                "{\n"
                "\tconst struct cred *cred;\n\n"
                "\tWARN_ON(oom_killer_disabled);",
                "Direct-302 oom cred lisa",
            )
        else:
            raise RuntimeError("Direct-302 oom: no supported mark_oom_victim layout")

    uid_trace = (
        "\tcred = get_task_cred(tsk);\n"
        "\ttrace_mark_victim(tsk, cred->uid.val);\n"
        "\tput_cred(cred);\n"
    )
    if uid_trace not in s:
        if "\ttrace_mark_victim(tsk->pid);\n" in s:
            s = once(
                s,
                "\ttrace_mark_victim(tsk->pid);\n",
                uid_trace,
                "Direct-302 oom victim UID trace",
            )
        elif "trace_mark_victim(tsk, cred->uid.val);" not in s:
            raise RuntimeError("Direct-302 oom: victim trace endpoint anchor missing")

    for token in (
        "touch_softlockup_watchdog();",
        "const struct cred *cred;",
        "get_task_cred(tsk);",
        "trace_mark_victim(tsk, cred->uid.val);",
        "put_cred(cred);",
    ):
        if token not in s:
            raise RuntimeError(f"Direct-302 oom endpoint missing {token}")

    p.write_text(s)



def adapt_slub(root: Path):
    p = root / "mm/slub.c"
    s = p.read_text()

    start = s.find("void object_err(struct kmem_cache *s, struct page *page,")
    if start < 0:
        raise RuntimeError("Direct-302 slub: object_err start not found")
    end = s.find("\nstatic __printf(3, 4) void slab_err", start)
    if end < 0:
        raise RuntimeError("Direct-302 slub: object_err end not found")

    fn = s[start:end]
    endpoint = (
        "\tif (!object || !check_valid_pointer(s, page, object)) {\n"
        "\t\tprint_page_info(page);\n"
        "\t\tpr_err(\"Invalid pointer 0x%p\\n\", object);\n"
        "\t} else {\n"
        "\t\tprint_trailer(s, page, object);\n"
        "\t}\n"
    )

    if "check_valid_pointer(s, page, object)" not in fn:
        old = "\tprint_trailer(s, page, object);\n"
        if fn.count(old) != 1:
            raise RuntimeError(
                f"Direct-302 slub: object_err trailer anchor count={fn.count(old)}"
            )
        fn = fn.replace(old, endpoint, 1)

    for token in (
        "check_valid_pointer(s, page, object)",
        "print_page_info(page);",
        "pr_err(\"Invalid pointer 0x%p\\n\", object);",
        "print_trailer(s, page, object);",
    ):
        if token not in fn:
            raise RuntimeError(f"Direct-302 slub endpoint missing {token}")

    s = s[:start] + fn + s[end:]
    p.write_text(s)


def adapt(root: Path, path: str, target_ref: str, target_blob, reviewed_segments):
    segments = tuple(reviewed_segments)

    if path == "Makefile":
        adapt_makefile(root)
        return "DIRECT_302_MAKEFILE"

    if path == "arch/arm64/include/asm/cputype.h":
        adapt_cputype(root)
        return "DIRECT_302_CPUTYPE_B_D"

    if path == "drivers/platform/Kconfig":
        adapt_platform_kconfig(root)
        return "DIRECT_302_PLATFORM_KCONFIG_B"

    if path == "drivers/platform/Makefile":
        adapt_platform_makefile(root)
        return "DIRECT_302_PLATFORM_MAKEFILE_B"

    if path == "drivers/hid/hid-ids.h":
        adapt_hid_ids(root)
        return "DIRECT_302_HID_A_B_D"

    if path == "drivers/media/pci/ivtv/ivtv-streams.c":
        adapt_ivtv_streams(root)
        return "DIRECT_302_IVTV_D"

    if path == "drivers/mmc/host/sdhci-msm.c":
        adapt_sdhci_msm(root)
        return "DIRECT_302_SDHCI_MSM_D"

    if path == "drivers/soc/qcom/rpmh-rsc.c":
        adapt_rpmh_rsc(root)
        return "DIRECT_302_RPMH_RSC_D"

    if path == "drivers/usb/core/quirks.c":
        adapt_usb_core_quirks(root)
        return "DIRECT_302_USB_CORE_QUIRKS_A_B_C_D"

    if path == "drivers/usb/dwc3/dwc3-qcom.c":
        adapt_dwc3_qcom(root)
        return "DIRECT_302_DWC3_QCOM_C"

    if path == "drivers/usb/dwc3/gadget.c":
        adapt_dwc3_gadget(root)
        return "DIRECT_302_DWC3_GADGET_A_B_C"

    if path == "mm/oom_kill.c":
        adapt_oom_kill(root)
        return "DIRECT_302_OOM_KILL_A"

    if path == "mm/slub.c":
        adapt_slub(root)
        return "DIRECT_302_SLUB_C"

    if path == "drivers/usb/gadget/function/f_fs.c":
        adapt_functionfs(root)
        return "DIRECT_302_FUNCTIONFS_A_D"

    if path == "drivers/usb/gadget/function/f_ncm.c":
        adapt_function_ncm(root)
        return "DIRECT_302_FUNCTION_NCM_D"

    if path == "drivers/usb/host/xhci-plat.c":
        adapt_xhci_plat(root)
        return "DIRECT_302_XHCI_PLAT_C_D"

    if path == "fs/ext4/dir.c":
        adapt_ext4_dir(root)
        return "DIRECT_302_EXT4_DIR_B"

    if path == "include/linux/pid.h":
        adapt_pid_h(root)
        return "DIRECT_302_PID_H_B"

    if path == "include/linux/usb/usbnet.h":
        adapt_usbnet_h(root)
        return "DIRECT_302_USBNET_H_C"

    if path == "include/net/sock.h":
        adapt_net_sock_h(root)
        return "DIRECT_302_NET_SOCK_H_D"

    if path == "kernel/sched/fair.c":
        adapt_sched_fair(root)
        return "DIRECT_302_SCHED_FAIR_D"

    if path == "kernel/softirq.c":
        adapt_softirq(root)
        return "DIRECT_302_SOFTIRQ_A"

    if path == "kernel/time/posix-timers.c":
        adapt_posix_timers(root)
        return "DIRECT_302_POSIX_TIMERS_B"

    # Reuse historical reviewed adapters only when the path is affected by that
    # single provenance segment. Multi-segment paths need a Direct-302 endpoint
    # adapter so later stable semantics cannot be silently skipped.
    if segments == ("A",) and batch_a.MANUAL.get(path) == "ADAPT":
        batch_a.adapt(root, path, target_ref, target_blob)
        return "REUSED_BATCH_A_ADAPTER"

    if segments == ("B",) and batch_b.MANUAL.get(path) == "ADAPT":
        batch_b.adapt(root, path, target_ref, target_blob)
        return "REUSED_BATCH_B_ADAPTER"

    raise RuntimeError(
        f"{path}: reviewed Direct-302 ADAPT decision exists but source adapter "
        f"is not implemented yet (segments={','.join(segments)})"
    )
