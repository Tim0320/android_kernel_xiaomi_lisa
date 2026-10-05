from pathlib import Path

# STABLE_ONLY Batch B (5.4.292 -> 5.4.296) semantic adapters.
# Keep downstream Qualcomm/Xiaomi structure and apply only reviewed stable semantics.
MANUAL={
    "Makefile":"ADAPT",
    "arch/arm64/include/asm/cputype.h":"ADAPT",
    "drivers/hid/hid-ids.h":"ADAPT",
    "drivers/pinctrl/qcom/pinctrl-msm.c":"ADAPT",
}

def once(s,old,new,label):
    n=s.count(old)
    if n!=1:
        raise RuntimeError(f"{label}: anchor count={n}")
    return s.replace(old,new,1)

def adapt(root:Path,path:str,target_ref:str,target_blob):
    p=root/path
    s=p.read_text()
    if path=="Makefile":
        # The downstream top-level Makefile carries vendor kbuild changes, so replacing
        # it with upstream would be incorrect. Stable Batch B only needs the release
        # identity advanced after Batch A has already established SUBLEVEL 292.
        s=once(s,"SUBLEVEL = 292\n","SUBLEVEL = 296\n","Batch B Makefile SUBLEVEL")
    elif path=="arch/arm64/include/asm/cputype.h":
        # Stable 5.4.293 adds Cortex-A76AE MIDR definitions. Lisa already carries many
        # newer vendor CPU IDs, so keep that downstream superset and insert only the
        # two stable-provenance definitions also present in AOSP 5.4.293+ and MiYume 5.4.302.
        s=once(s,
            "#define ARM_CPU_PART_CORTEX_A77\\t\\t0xD0D\\n",
            "#define ARM_CPU_PART_CORTEX_A77\\t\\t0xD0D\\n#define ARM_CPU_PART_CORTEX_A76AE\\t0xD0E\\n",
            "Batch B Cortex-A76AE part")
        s=once(s,
            "#define MIDR_CORTEX_A77\\tMIDR_CPU_MODEL(ARM_CPU_IMP_ARM, ARM_CPU_PART_CORTEX_A77)\\n",
            "#define MIDR_CORTEX_A77\\tMIDR_CPU_MODEL(ARM_CPU_IMP_ARM, ARM_CPU_PART_CORTEX_A77)\\n#define MIDR_CORTEX_A76AE\\tMIDR_CPU_MODEL(ARM_CPU_IMP_ARM, ARM_CPU_PART_CORTEX_A76AE)\\n",
            "Batch B Cortex-A76AE MIDR")
    elif path=="drivers/hid/hid-ids.h":
        # Stable 5.4.293-5.4.296 adds three HID identity groups. Keep Lisa's
        # vendor HID table and insert only the stable-provenance IDs; hid-quirks.c
        # carries the matching quirk behavior through the normal three-way merge.
        s=once(s,
            "#define USB_VENDOR_ID_ACTIONSTAR\\t0x2101\\n#define USB_DEVICE_ID_ACTIONSTAR_1011\\t0x1011\\n",
            "#define USB_VENDOR_ID_ACTIONSTAR\\t0x2101\\n#define USB_DEVICE_ID_ACTIONSTAR_1011\\t0x1011\\n\\n#define USB_VENDOR_ID_ADATA_XPG 0x125f\\n#define USB_VENDOR_ID_ADATA_XPG_WL_GAMING_MOUSE 0x7505\\n#define USB_VENDOR_ID_ADATA_XPG_WL_GAMING_MOUSE_DONGLE 0x7506\\n",
            "Batch B ADATA XPG HID IDs")
        s=once(s,
            "#define USB_DEVICE_ID_CHICONY_ACER_SWITCH12\\t0x1421\\n",
            "#define USB_DEVICE_ID_CHICONY_ACER_SWITCH12\\t0x1421\\n#define USB_DEVICE_ID_CHICONY_HP_5MP_CAMERA\\t0xb824\\n#define USB_DEVICE_ID_CHICONY_HP_5MP_CAMERA2\\t0xb82c\\n",
            "Batch B Chicony HP 5MP HID IDs")
        s=once(s,
            "#define USB_VENDOR_ID_SIGNOTEC\\t\\t\\t0x2133\\n#define USB_DEVICE_ID_SIGNOTEC_VIEWSONIC_PD1011\\t0x0018\\n",
            "#define USB_VENDOR_ID_SIGNOTEC\\t\\t\\t0x2133\\n#define USB_DEVICE_ID_SIGNOTEC_VIEWSONIC_PD1011\\t0x0018\\n\\n#define USB_VENDOR_ID_SMARTLINKTECHNOLOGY              0x4c4a\\n#define USB_DEVICE_ID_SMARTLINKTECHNOLOGY_4155         0x4155\\n",
            "Batch B SmartlinkTechnology HID IDs")
    elif path=="drivers/pinctrl/qcom/pinctrl-msm.c":
        # Stable 5.4.292->5.4.296 adds an IRQ-valid mask which excludes GPIO
        # groups whose intr_detection_width is neither 1 nor 2. Lisa carries
        # extra downstream direct-connect/wake handling, so preserve that flow
        # and insert only the stable valid-mask callback + gpio_irq_chip hook.
        irq_valid_mask = """static void msm_gpio_irq_init_valid_mask(struct gpio_chip *gc,
                                         unsigned long *valid_mask,
                                         unsigned int ngpios)
{
        struct msm_pinctrl *pctrl = gpiochip_get_data(gc);
        const struct msm_pingroup *g;
        int i;

        bitmap_fill(valid_mask, ngpios);

        for (i = 0; i < ngpios; i++) {
                g = &pctrl->soc->groups[i];

                if (g->intr_detection_width != 1 &&
                    g->intr_detection_width != 2)
                        clear_bit(i, valid_mask);
        }
}

"""
        s=once(s,
            "static void msm_dirconn_cfg_reg(struct irq_data *d, u32 offset)\n",
            irq_valid_mask + "static void msm_dirconn_cfg_reg(struct irq_data *d, u32 offset)\n",
            "Batch B pinctrl IRQ valid-mask callback")
        s=once(s,
            "\tgirq->parents[0] = pctrl->irq;\n",
            "\tgirq->parents[0] = pctrl->irq;\n\tgirq->init_valid_mask = msm_gpio_irq_init_valid_mask;\n",
            "Batch B pinctrl IRQ valid-mask hook")
    else:
        raise RuntimeError("unreviewed Batch B semantic conflict: "+path)
    p.write_text(s)
