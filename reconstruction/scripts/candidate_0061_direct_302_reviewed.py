# Reviewed Direct-302 semantic decisions.
#
# A decision is reusable only when all provenance segments affecting the path
# are contained in reviewed_segments. This registry covers the 33 semantic
# paths reported by Direct-302 run 37363542334 attempt 3.

REVIEWED_SEMANTICS = {
    "Documentation/devicetree/bindings/mmc/mmc-controller.yaml": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "A"
        ],
        "reason": "Preserve downstream binding edits and carry the stable SDIO function-number clarification."
    },
    "Makefile": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "A",
            "B",
            "C",
            "D"
        ],
        "reason": "Carry the complete 5.4.302 stable kbuild endpoint while preserving Lisa's Clang 11/downstream toolchain contract: A userspace-linker --ld-path handling, B Clang warning/builtin fixes, C CLANG_FLAGS propagation through KBUILD_CPPFLAGS, and D SUBLEVEL=302."
    },
    "arch/arm64/include/asm/cputype.h": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "B",
            "D"
        ],
        "reason": "Add stable Cortex-A76AE and Neoverse-V3AE identifiers while preserving Lisa downstream Qualcomm/Kryo CPU IDs."
    },
    "drivers/base/regmap/regmap.c": {
        "classification": "NOT_APPLICABLE",
        "resolution": "NOT_APPLICABLE",
        "reviewed_segments": [
            "D"
        ],
        "reason": "The stable config-pointer guard cleanup targets an upstream init branch that Lisa's downstream bus-aware regmap flow no longer has."
    },
    "drivers/clk/qcom/clk-alpha-pll.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "A"
        ],
        "reason": "Preserve downstream PLL flow and add stable alpha_mode_mask handling."
    },
    "drivers/hid/hid-ids.h": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "A",
            "B",
            "D"
        ],
        "reason": "Merge the stable A/B/D HID identity additions and renames while preserving Lisa vendor-specific IDs and downstream quirks."
    },
    "drivers/media/pci/ivtv/ivtv-streams.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "D"
        ],
        "reason": "Apply the stable PCI_DMA_* to DMA_* API migration without replacing Lisa's downstream VFL_TYPE_GRABBER behavior."
    },
    "drivers/mmc/host/sdhci-msm.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "D"
        ],
        "reason": "Add the stable SDR50 tuning requirement/HC-select semantics while preserving Lisa SM7325/Yupik Qualcomm tuning helpers and downstream accessors."
    },
    "drivers/pinctrl/qcom/pinctrl-msm.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "B"
        ],
        "reason": "Preserve downstream direct-connect/wake handling and add stable IRQ valid-mask semantics."
    },
    "drivers/platform/Kconfig": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "B"
        ],
        "reason": "Add Surface platform Kconfig source while retaining Lisa drivers/platform/msm source."
    },
    "drivers/platform/Makefile": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "B"
        ],
        "reason": "Add CONFIG_SURFACE_PLATFORMS surface/ entry while retaining CONFIG_ARCH_QCOM msm/."
    },
    "drivers/soc/qcom/rpmh-rsc.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "D"
        ],
        "reason": "Carry the stable completed-TCS AMC trigger cleanup while preserving Lisa downstream ACTIVE_TCS/IRQ handling semantics."
    },
    "drivers/soc/qcom/socinfo.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "A"
        ],
        "reason": "Preserve Lisa socinfo API and add stable item-size-aware serial-number bounds."
    },
    "drivers/usb/core/quirks.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "A",
            "B",
            "C",
            "D"
        ],
        "reason": "Merge the complete stable USB quirk endpoint while preserving Lisa downstream quirks, including combining stable delay-init semantics with existing NO_LPM behavior where both apply."
    },
    "drivers/usb/dwc3/dwc3-qcom.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "C"
        ],
        "reason": "Adopt the stable post-deassert reset/error-path semantics without replacing Lisa Qualcomm GDSC and vendor integration."
    },
    "drivers/usb/dwc3/gadget.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "A",
            "B",
            "C"
        ],
        "reason": "Carry stable disconnect, transfer-not-ready/event-length and USB2 PHY safety semantics while preserving Lisa Qualcomm GSI/FIFO/doorbell cleanup and downstream timeout behavior."
    },
    "drivers/usb/gadget/function/f_fs.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "A",
            "D"
        ],
        "reason": "Carry stable FunctionFS null/state safety changes while preserving Lisa downstream IPC and vendor I/O behavior."
    },
    "drivers/usb/gadget/function/f_ncm.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "D"
        ],
        "reason": "Carry the stable MAC-string attachment ordering while preserving Lisa NCM gadget behavior."
    },
    "drivers/usb/host/xhci-plat.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "C",
            "D"
        ],
        "reason": "Add stable broken-stream capability gating and autosuspend semantics while preserving Lisa's downstream autosuspend timing."
    },
    "fs/ext4/dir.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "B"
        ],
        "reason": "Retain Lisa fake-dir/ext4_dir_rec_len semantics, use next_offset bounds checks, and reject dot as the last data-block entry."
    },
    "include/linux/pid.h": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "B"
        ],
        "reason": "Add pidfd_prepare prototype and pid_has_task helper without replacing downstream pid header content."
    },
    "include/linux/usb/usbnet.h": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "C"
        ],
        "reason": "Add EVENT_LINK_CARRIER_ON=14 while preserving Lisa's Android KABI layout and downstream speed fields."
    },
    "include/net/sock.h": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "D"
        ],
        "reason": "Carry the stable socket/module-owner lifetime and lockdep endpoint while preserving Android vendor hooks and KABI layout."
    },
    "kernel/cpu.c": {
        "classification": "STABLE_ONLY",
        "resolution": "NOT_APPLICABLE",
        "reviewed_segments": [
            "A"
        ],
        "reason": "The stable hrtimer CPUHP callback belongs to a newer hotplug model that Lisa does not use."
    },
    "kernel/gen_kheaders.sh": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "A"
        ],
        "reason": "Preserve Lisa kheaders packaging and add stable AFS/NFS silly-rename exclusions."
    },
    "kernel/sched/fair.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "D"
        ],
        "reason": "Carry only the stable sched_balance_newidle/rq-flags safety refactor; preserve Lisa WALT/MIGT scheduler behavior and keep touch/performance tuning out of the stable gate."
    },
    "kernel/softirq.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "A"
        ],
        "reason": "Port stable tasklet callback API support while preserving downstream softirq behavior."
    },
    "kernel/time/hrtimer.c": {
        "classification": "STABLE_ONLY",
        "resolution": "NOT_APPLICABLE",
        "reviewed_segments": [
            "A"
        ],
        "reason": "The stable CPUHP_AP_HRTIMERS_DYING change targets the newer upstream hotplug model; Lisa retains CPUHP_HRTIMERS_PREPARE."
    },
    "kernel/time/posix-timers.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "B"
        ],
        "reason": "Add cond_resched to the timer-ID allocation retry loop."
    },
    "mm/oom_kill.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "A"
        ],
        "reason": "Port stable OOM soft-lockup and trace semantics while preserving downstream OOM hooks."
    },
    "mm/slub.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "C"
        ],
        "reason": "Add the stable invalid-object-pointer guard before trailer access while preserving Lisa/QCOM minidump and downstream slab diagnostics."
    },
    "mm/zsmalloc.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "C"
        ],
        "reason": "Use the stable zeroed zspage allocation and !CONFIG_COMPACTION GFP semantics while preserving Lisa __GFP_CMA/__GFP_OFFLINABLE exclusions."
    },
    "net/core/sock.c": {
        "classification": "STABLE_ONLY",
        "resolution": "ADAPT",
        "reviewed_segments": [
            "B",
            "D"
        ],
        "reason": "Carry stable PROTO_INUSE_NR bounds, socket-owner/trace fixes and reduced backlog cond_resched frequency while preserving Android vendor hooks and downstream socket behavior."
    }
}
