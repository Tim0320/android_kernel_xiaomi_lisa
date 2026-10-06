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
