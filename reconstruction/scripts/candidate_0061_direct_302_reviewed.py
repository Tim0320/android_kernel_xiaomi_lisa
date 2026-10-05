# Reviewed Direct-302 semantic decisions.
#
# A decision is reusable only when all provenance segments affecting the path
# are contained in reviewed_segments. Later C/D changes on the same path must
# remain unresolved until reviewed separately.

REVIEWED_SEMANTICS = {
    "Documentation/devicetree/bindings/mmc/mmc-controller.yaml": {
        "classification": "STABLE_ONLY", "resolution": "ADAPT",
        "reviewed_segments": ["A"],
        "reason": "Preserve downstream binding edits and carry the stable SDIO function-number clarification.",
    },
    "drivers/clk/qcom/clk-alpha-pll.c": {
        "classification": "STABLE_ONLY", "resolution": "ADAPT",
        "reviewed_segments": ["A"],
        "reason": "Preserve downstream PLL flow and add stable alpha_mode_mask handling.",
    },
    "drivers/pinctrl/qcom/pinctrl-msm.c": {
        "classification": "STABLE_ONLY", "resolution": "ADAPT",
        "reviewed_segments": ["B"],
        "reason": "Preserve downstream direct-connect/wake handling and add stable IRQ valid-mask semantics.",
    },
    "drivers/soc/qcom/socinfo.c": {
        "classification": "STABLE_ONLY", "resolution": "ADAPT",
        "reviewed_segments": ["A"],
        "reason": "Preserve Lisa socinfo API and add stable item-size-aware serial-number bounds.",
    },
    "drivers/platform/Kconfig": {
        "classification": "STABLE_ONLY", "resolution": "ADAPT",
        "reviewed_segments": ["B"],
        "reason": "Add Surface platform Kconfig source while retaining Lisa drivers/platform/msm source.",
    },
    "drivers/platform/Makefile": {
        "classification": "STABLE_ONLY", "resolution": "ADAPT",
        "reviewed_segments": ["B"],
        "reason": "Add CONFIG_SURFACE_PLATFORMS surface/ entry while retaining CONFIG_ARCH_QCOM msm/.",
    },
    "fs/ext4/dir.c": {
        "classification": "STABLE_ONLY", "resolution": "ADAPT",
        "reviewed_segments": ["B"],
        "reason": "Retain Lisa fake-dir/ext4_dir_rec_len semantics, use next_offset bounds checks, and reject dot as the last data-block entry.",
    },
    "include/linux/pid.h": {
        "classification": "STABLE_ONLY", "resolution": "ADAPT",
        "reviewed_segments": ["B"],
        "reason": "Add pidfd_prepare prototype and pid_has_task helper without replacing downstream pid header content.",
    },
    "kernel/time/posix-timers.c": {
        "classification": "STABLE_ONLY", "resolution": "ADAPT",
        "reviewed_segments": ["B"],
        "reason": "Add cond_resched to the timer-ID allocation retry loop.",
    },
    "kernel/cpu.c": {
        "classification": "STABLE_ONLY", "resolution": "NOT_APPLICABLE",
        "reviewed_segments": ["A"],
        "reason": "The stable hrtimer CPUHP callback belongs to a newer hotplug model that Lisa does not use.",
    },
    "kernel/gen_kheaders.sh": {
        "classification": "STABLE_ONLY", "resolution": "ADAPT",
        "reviewed_segments": ["A"],
        "reason": "Preserve Lisa kheaders packaging and add stable AFS/NFS silly-rename exclusions.",
    },
    "kernel/softirq.c": {
        "classification": "STABLE_ONLY", "resolution": "ADAPT",
        "reviewed_segments": ["A"],
        "reason": "Port stable tasklet callback API support while preserving downstream softirq behavior.",
    },
    "kernel/time/hrtimer.c": {
        "classification": "STABLE_ONLY", "resolution": "NOT_APPLICABLE",
        "reviewed_segments": ["A"],
        "reason": "The stable CPUHP_AP_HRTIMERS_DYING change targets the newer upstream hotplug model; Lisa retains CPUHP_HRTIMERS_PREPARE.",
    },
    "mm/oom_kill.c": {
        "classification": "STABLE_ONLY", "resolution": "ADAPT",
        "reviewed_segments": ["A"],
        "reason": "Port stable OOM soft-lockup and trace semantics while preserving downstream OOM hooks.",
    },
}
