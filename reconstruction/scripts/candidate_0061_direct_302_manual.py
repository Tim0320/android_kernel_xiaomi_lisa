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


def adapt(root: Path, path: str, target_ref: str, target_blob, reviewed_segments):
    segments = tuple(reviewed_segments)

    if path == "Makefile":
        adapt_makefile(root)
        return "DIRECT_302_MAKEFILE"

    if path == "arch/arm64/include/asm/cputype.h":
        adapt_cputype(root)
        return "DIRECT_302_CPUTYPE_B_D"

    if path == "drivers/hid/hid-ids.h":
        adapt_hid_ids(root)
        return "DIRECT_302_HID_A_B_D"

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
