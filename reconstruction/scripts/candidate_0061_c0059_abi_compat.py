#!/usr/bin/env python3
"""Restore Candidate0059 ABI/runtime compatibility surface.

This is intentionally side-effect-free: callers pass the package root and
kernel source root.  It preserves the frozen Candidate0059 ABI while leaving
official Stable Batch A source changes intact.
"""
from pathlib import Path


def _patch_mtdoops(kernel: Path) -> None:
    p = kernel / "drivers/mtd/mtdoops.c"
    s = p.read_text()
    if "EXPORT_SYMBOL_GPL(lisa_mtdoops_checkpoint);" in s:
        return

    anchor = "static void mtdoops_notify_add(struct mtd_info *mtd)\n"
    if s.count(anchor) != 1:
        raise RuntimeError(f"mtdoops checkpoint insertion anchor count={s.count(anchor)}")

    helper = r'''void lisa_mtdoops_checkpoint(const char *tag)
{
	struct mtdoops_context *cxt = &oops_cxt;
	size_t len = 0;

	if (!cxt->mtd || !cxt->oops_buf)
		return;

	/*
	 * Candidate0059 compatibility checkpoint: serialize against the normal
	 * deferred writer, snapshot the current printk ring, and persist it using
	 * the regular non-panic MTD path before returning.
	 */
	flush_work(&cxt->work_write);
	pr_emerg("LISA_C0059_COMPAT_CHECKPOINT tag=%s\n", tag);
	kmsg_dump_rewind(&cxt->dump);
	if (kmsg_dump_get_buffer(&cxt->dump, true,
				 cxt->oops_buf + MTDOOPS_HEADER_SIZE,
				 record_size - MTDOOPS_HEADER_SIZE, &len) && len)
		mtdoops_write(cxt, 0);
}
EXPORT_SYMBOL_GPL(lisa_mtdoops_checkpoint);

'''
    p.write_text(s.replace(anchor, helper + anchor, 1))


def _patch_qcom_download_mode(kernel: Path) -> None:
    hp = kernel / "include/linux/qcom_scm.h"
    h = hp.read_text()
    if "qcom_scm_get_download_mode" not in h:
        old = """extern void qcom_scm_set_download_mode(enum qcom_download_mode mode,
				       phys_addr_t tcsr_boot_misc);
"""
        new = old + """extern int qcom_scm_get_download_mode(unsigned int *mode,
				      phys_addr_t tcsr_boot_misc);
"""
        if h.count(old) != 1:
            raise RuntimeError(f"qcom_scm public header anchor count={h.count(old)}")
        h = h.replace(old, new, 1)

        old_stub = """static inline void qcom_scm_set_download_mode(enum qcom_download_mode mode,
		phys_addr_t tcsr_boot_misc) {}
"""
        new_stub = old_stub + """static inline int qcom_scm_get_download_mode(unsigned int *mode,
		phys_addr_t tcsr_boot_misc) { return -ENODEV; }
"""
        if old_stub in h:
            h = h.replace(old_stub, new_stub, 1)
        hp.write_text(h)

    cp = kernel / "drivers/firmware/qcom_scm.c"
    c = cp.read_text()
    if "EXPORT_SYMBOL(qcom_scm_get_download_mode);" in c:
        return

    anchor = """EXPORT_SYMBOL(qcom_scm_set_download_mode);

"""
    if c.count(anchor) != 1:
        raise RuntimeError(f"qcom_scm getter insertion anchor count={c.count(anchor)}")

    getter = r'''int qcom_scm_get_download_mode(unsigned int *mode,
			       phys_addr_t tcsr_boot_misc)
{
	struct device *dev = __scm ? __scm->dev : NULL;
	phys_addr_t addr;

	if (!mode)
		return -EINVAL;

	addr = tcsr_boot_misc;
	if (!addr && __scm)
		addr = __scm->dload_mode_addr;
	if (!addr)
		return -EINVAL;

	return __qcom_scm_io_readl(dev, addr, mode);
}
EXPORT_SYMBOL(qcom_scm_get_download_mode);

'''
    cp.write_text(c.replace(anchor, anchor + getter, 1))



def _patch_timer_delete_sync_compat(kernel: Path) -> None:
    """Bridge upstream 5.4 stable timer_delete_sync() callers to Lisa KMI.

    Upstream 5.4.289+ already exposes timer_delete_sync() and keeps
    del_timer_sync() as the compatibility spelling.  Lisa's downstream base
    still exports del_timer_sync() directly.  Do not rename the exported Lisa
    implementation: provide a header-only wrapper so newer stable call-sites
    compile without adding/removing a Module.symvers symbol.
    """
    p = kernel / "include/linux/timer.h"
    s = p.read_text()

    if "static inline int timer_delete_sync(struct timer_list *timer)" in s:
        return
    if "extern int timer_delete_sync(struct timer_list *timer);" in s:
        return

    anchor = """#if defined(CONFIG_SMP) || defined(CONFIG_PREEMPT_RT)
	extern int del_timer_sync(struct timer_list *timer);
#else
# define del_timer_sync(t)			 del_timer(t)
#endif

"""
    if s.count(anchor) != 1:
        raise RuntimeError(
            f"timer_delete_sync compatibility anchor count={s.count(anchor)}"
        )

    wrapper = anchor + """/*
 * Candidate0061 compatibility bridge:
 * stable 5.4 call-sites use timer_delete_sync(), while the frozen Lisa KMI
 * still exports del_timer_sync().  Keep the exported ABI unchanged.
 */
static inline int timer_delete_sync(struct timer_list *timer)
{
	return del_timer_sync(timer);
}

"""
    p.write_text(s.replace(anchor, wrapper, 1))




def _patch_irq_affinity_hint_compat(kernel: Path) -> None:
    """Restore the Candidate0059 irq_set_affinity_hint export after Stable.

    Stable commit 7b2a6732 keeps the deprecated API as a header inline wrapper
    over __irq_apply_affinity_hint(), which is correct upstream behaviour but
    removes the exported Candidate0059 KMI symbol.  Preserve the new Stable
    interfaces and semantics, while restoring only the legacy out-of-line
    wrapper/export.
    """
    hp = kernel / "include/linux/interrupt.h"
    cp = kernel / "kernel/irq/manage.c"
    h = hp.read_text()
    c = cp.read_text()

    if "EXPORT_SYMBOL_GPL(irq_set_affinity_hint);" in c:
        return

    inline = """static inline int irq_set_affinity_hint(unsigned int irq, const struct cpumask *m)
{
\treturn irq_set_affinity_and_hint(irq, m);
}
"""
    extern = """extern int irq_set_affinity_hint(unsigned int irq,
\t\t\t\t const struct cpumask *m);
"""
    if inline in h:
        h = h.replace(inline, extern, 1)
    elif extern not in h:
        raise RuntimeError("irq_set_affinity_hint Stable inline/compat extern anchor missing")

    anchor = """EXPORT_SYMBOL_GPL(__irq_apply_affinity_hint);

"""
    if c.count(anchor) != 1:
        raise RuntimeError(
            f"irq_set_affinity_hint implementation anchor count={c.count(anchor)}"
        )
    compat = anchor + """/*
 * Candidate0061 KMI compatibility: keep Stable's new affinity-hint core,
 * but retain the Candidate0059 exported deprecated wrapper.
 */
int irq_set_affinity_hint(unsigned int irq, const struct cpumask *m)
{
\treturn irq_set_affinity_and_hint(irq, m);
}
EXPORT_SYMBOL_GPL(irq_set_affinity_hint);

"""
    cp.write_text(c.replace(anchor, compat, 1))
    hp.write_text(h)


def _patch_qdisc_warn_nonwc_compat(kernel: Path) -> None:
    """Restore qdisc_warn_nonwc export without reverting the QFQ Stable fix.

    Stable commit 71d84658 moved qdisc_warn_nonwc() into pkt_sched.h so the
    new shared qdisc_peek_len() helper can be used by QFQ.  Keep qdisc_peek_len
    and the QFQ null-deref fix, but make qdisc_warn_nonwc out-of-line again so
    the frozen Candidate0059 KMI export remains available.
    """
    hp = kernel / "include/net/pkt_sched.h"
    cp = kernel / "net/sched/sch_api.c"
    h = hp.read_text()
    c = cp.read_text()

    if "EXPORT_SYMBOL(qdisc_warn_nonwc);" in c:
        return

    inline = """static inline void qdisc_warn_nonwc(const char *txt, struct Qdisc *qdisc)
{
\tif (!(qdisc->flags & TCQ_F_WARN_NONWC)) {
\t\tpr_warn("%s: %s qdisc %X: is non-work-conserving?\\n",
\t\t\ttxt, qdisc->ops->id, qdisc->handle >> 16);
\t\tqdisc->flags |= TCQ_F_WARN_NONWC;
\t}
}
"""
    extern = "void qdisc_warn_nonwc(const char *txt, struct Qdisc *qdisc);\n"
    if inline in h:
        h = h.replace(inline, extern, 1)
    elif extern not in h:
        raise RuntimeError("qdisc_warn_nonwc Stable inline/compat extern anchor missing")

    anchor = "static enum hrtimer_restart qdisc_watchdog(struct hrtimer *timer)\n"
    if c.count(anchor) != 1:
        raise RuntimeError(
            f"qdisc_warn_nonwc implementation anchor count={c.count(anchor)}"
        )
    compat = """void qdisc_warn_nonwc(const char *txt, struct Qdisc *qdisc)
{
\tif (!(qdisc->flags & TCQ_F_WARN_NONWC)) {
\t\tpr_warn("%s: %s qdisc %X: is non-work-conserving?\\n",
\t\t\ttxt, qdisc->ops->id, qdisc->handle >> 16);
\t\tqdisc->flags |= TCQ_F_WARN_NONWC;
\t}
}
EXPORT_SYMBOL(qdisc_warn_nonwc);

"""
    cp.write_text(c.replace(anchor, compat + anchor, 1))
    hp.write_text(h)



def apply(root: Path, kernel: Path) -> None:
    _patch_mtdoops(kernel)
    _patch_qcom_download_mode(kernel)
    _patch_timer_delete_sync_compat(kernel)
    _patch_irq_affinity_hint_compat(kernel)
    _patch_qdisc_warn_nonwc_compat(kernel)

    m = (kernel / "drivers/mtd/mtdoops.c").read_text()
    qh = (kernel / "include/linux/qcom_scm.h").read_text()
    qc = (kernel / "drivers/firmware/qcom_scm.c").read_text()
    th = (kernel / "include/linux/timer.h").read_text()
    irqh = (kernel / "include/linux/interrupt.h").read_text()
    irqc = (kernel / "kernel/irq/manage.c").read_text()
    qdisc_h = (kernel / "include/net/pkt_sched.h").read_text()
    qcdisc = (kernel / "net/sched/sch_api.c").read_text()
    gates = [
        ("mtd checkpoint export", "EXPORT_SYMBOL_GPL(lisa_mtdoops_checkpoint);", m),
        ("mtd checkpoint persistence", "mtdoops_write(cxt, 0);", m),
        ("download-mode prototype", "qcom_scm_get_download_mode(unsigned int *mode", qh),
        ("download-mode implementation", "__qcom_scm_io_readl(dev, addr, mode)", qc),
        ("download-mode export", "EXPORT_SYMBOL(qcom_scm_get_download_mode);", qc),
        ("timer-delete compatibility wrapper", "static inline int timer_delete_sync(struct timer_list *timer)", th),
        ("timer-delete preserves Lisa implementation", "return del_timer_sync(timer);", th),
        ("irq affinity legacy prototype", "irq_set_affinity_hint(unsigned int irq", irqh),
        ("irq affinity legacy export", "EXPORT_SYMBOL_GPL(irq_set_affinity_hint);", irqc),
        ("qdisc legacy prototype", "void qdisc_warn_nonwc(const char *txt, struct Qdisc *qdisc);", qdisc_h),
        ("qdisc legacy export", "EXPORT_SYMBOL(qdisc_warn_nonwc);", qcdisc),
    ]
    if "__irq_apply_affinity_hint" in irqh:
        gates.append(
            ("irq affinity Stable core retained",
             "__irq_apply_affinity_hint(unsigned int irq", irqh)
        )
    if "static inline unsigned int qdisc_peek_len" in qdisc_h:
        gates.append(
            ("qdisc Stable peek helper retained",
             "static inline unsigned int qdisc_peek_len", qdisc_h)
        )
    for label, needle, body in gates:
        if needle not in body:
            raise RuntimeError(f"Candidate0059 ABI compatibility gate missing {label}: {needle}")

    (root / "candidate-0061-c0059-abi-compat.txt").write_text(
        "classification=MIXED_CONFLICT\n"
        "baseline=Candidate0059 r43da7c5 Module.symvers\n"
        "restored_exports=lisa_mtdoops_checkpoint,qcom_scm_get_download_mode,irq_set_affinity_hint,qdisc_warn_nonwc\n"
        "mtd_semantics=synchronous printk-ring persistence through normal mtdoops write path\n"
        "download_mode_semantics=read TCSR/dload-mode address through __qcom_scm_io_readl\n"
        "stable_policy=do not revert official Batch A xHCI/fs/softirq/flow-offload ABI changes\n"
        "timer_api_compat=header-only timer_delete_sync wrapper over Lisa del_timer_sync; no new exported timer symbol\n"
        "irq_affinity_compat=Stable __irq_apply_affinity_hint retained; deprecated Candidate0059 irq_set_affinity_hint export restored\n"
        "qdisc_compat=Stable qdisc_peek_len/QFQ fix retained; Candidate0059 qdisc_warn_nonwc export restored out-of-line\n"
        "C0061_C0059_ABI_COMPAT_GATE=PASS\n"
    )
