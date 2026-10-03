"""Candidate0054: raw first-fault capture, independent of symbol/console output."""
from pathlib import Path
import re

HEADER = r'''/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _LINUX_LISA_FAULT_CAPTURE_H
#define _LINUX_LISA_FAULT_CAPTURE_H
#include <linux/types.h>
#define LISA_ARM64_FAULT_TEXT_MAX 1280
size_t lisa_arm64_fault_copy(char *buf, size_t capacity);
#endif
'''

FAULT_HELPER = r'''
/* Diagnostic-only first-fault latch: no allocation, sleeping lock or I/O.
 * A separate mtdoops worker can copy this even if the faulting CPU never
 * returns from printk/console/symbol lookup. Never dereference saved task.
 */
struct lisa_arm64_raw_fault {
	unsigned long addr, esr, pc, lr, sp, fp, pstate;
	unsigned long ktext, task, mpidr;
	unsigned long x[31];
};
static struct lisa_arm64_raw_fault lisa_first_fault;
static atomic_t lisa_first_fault_claim = ATOMIC_INIT(0);
static int lisa_first_fault_ready;

noinline size_t lisa_arm64_fault_copy(char *buf, size_t capacity)
{
	const struct lisa_arm64_raw_fault *f = &lisa_first_fault;
	size_t n;
	int i;

	if (!capacity || !smp_load_acquire(&lisa_first_fault_ready))
		return 0;
	n = scnprintf(buf, capacity,
		"\nLISA0054_RAW_FAULT saved=1 addr=%016lx esr=%08lx pc=%016lx lr=%016lx sp=%016lx fp=%016lx pstate=%016lx ktext=%016lx task=%016lx mpidr=%016lx\n",
		f->addr, f->esr, f->pc, f->lr, f->sp, f->fp, f->pstate,
		f->ktext, f->task, f->mpidr);
	for (i = 0; i < 31 && n < capacity - 1; i++)
		n += scnprintf(buf + n, capacity - n, "x%02d=%016lx%c",
			       i, f->x[i], ((i % 4) == 3 || i == 30) ? '\n' : ' ');
	return n;
}

static void lisa_arm64_capture_first_fault(unsigned long addr,
				unsigned int esr, struct pt_regs *regs)
{
	struct lisa_arm64_raw_fault *f = &lisa_first_fault;
	unsigned long flags;
	int i;

	if (atomic_cmpxchg(&lisa_first_fault_claim, 0, 1))
		return;
	f->addr = addr;
	f->esr = esr;
	f->pc = regs->pc;
	f->lr = regs->regs[30];
	f->sp = regs->sp;
	f->fp = regs->regs[29];
	f->pstate = regs->pstate;
	f->ktext = (unsigned long)_text;
	f->task = (unsigned long)current;
	f->mpidr = (unsigned long)read_sysreg(mpidr_el1);
	for (i = 0; i < 31; i++)
		f->x[i] = regs->regs[i];
	/* Publish before invoking any printk or backtrace path. */
	smp_store_release(&lisa_first_fault_ready, 1);

	/* IRQs disabled: no migration while printk_deferred uses per-CPU state.
	 * Numeric values only. In particular, no %pS, task->comm or task->pid.
	 */
	local_irq_save(flags);
	printk_deferred(KERN_EMERG
		"LISA0054_RAW_FAULT saved=1 addr=%016lx esr=%08lx pc=%016lx lr=%016lx sp=%016lx fp=%016lx ktext=%016lx task=%016lx mpidr=%016lx\n",
		f->addr, f->esr, f->pc, f->lr, f->sp, f->fp,
		f->ktext, f->task, f->mpidr);
	local_irq_restore(flags);
}

'''

MTD_OLD = r'''static void mtdoops_snapshot_write_fast(struct mtdoops_context *cxt, size_t len)
{
	struct mtd_info *mtd = cxt->mtd;
	size_t retlen = 0;
	size_t write_len = MTDOOPS_HEADER_SIZE + 8 + len;
	u32 *hdr = cxt->oops_buf;
	u32 *meta = (u32 *)(cxt->oops_buf + MTDOOPS_HEADER_SIZE);
	int ret;

	/* This fast path is safe only for the block2mtd RAM-like backend. */
'''
MTD_NEW = r'''static void mtdoops_snapshot_write_fast(struct mtdoops_context *cxt, size_t len)
{
	struct mtd_info *mtd = cxt->mtd;
	size_t retlen = 0;
	size_t write_len = MTDOOPS_HEADER_SIZE + 8 + len;
	u32 *hdr = cxt->oops_buf;
	u32 *meta = (u32 *)(cxt->oops_buf + MTDOOPS_HEADER_SIZE);
	char lisa_fault_text[LISA_ARM64_FAULT_TEXT_MAX];
	char *lisa_tail = cxt->oops_buf + MTDOOPS_HEADER_SIZE + 8;
	size_t lisa_fault_len, lisa_keep;
	int ret;

	/* Append the saved raw fault directly; no printk/symbol dependency.
	 * Keep only the newest log bytes that fit. Header length is updated
	 * below before the existing writer persists this same bounded record.
	 */
	lisa_fault_len = lisa_arm64_fault_copy(lisa_fault_text,
					    sizeof(lisa_fault_text));
	if (lisa_fault_len) {
		lisa_keep = min_t(size_t, len,
				 MTDOOPS_FAST_TAIL_BYTES - lisa_fault_len);
		memmove(lisa_tail, lisa_tail + len - lisa_keep, lisa_keep);
		memcpy(lisa_tail + lisa_keep, lisa_fault_text, lisa_fault_len);
		len = lisa_keep + lisa_fault_len;
		write_len = MTDOOPS_HEADER_SIZE + 8 + len;
	}

	/* This fast path is safe only for the block2mtd RAM-like backend. */
'''

MODULE_MAP = r'''	/* Capture relocation ranges while module metadata is known-valid.
	 * Offline decoding need not walk module/kallsyms lists during a fault.
	 */
	pr_info("LISA0054_MODULE name=%s core=%016lx size=%x text=%x init=%016lx init_size=%x\n",
		mod->name, (unsigned long)mod->core_layout.base,
		mod->core_layout.size, mod->core_layout.text_size,
		(unsigned long)mod->init_layout.base, mod->init_layout.size);
	trace_module_load(mod);
'''


def once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"Candidate0054 {label}: expected one anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def apply(root: Path, kernel: Path) -> None:
    """Called after the unchanged base's fast-mtdoops and QGKI patches."""
    cfg = (kernel / "out/.config").read_text()
    for item in ("CONFIG_ARM64=y\n", "CONFIG_MTD_OOPS=y\n", "CONFIG_PRINTK=y\n"):
        if item not in cfg:
            raise RuntimeError(f"Candidate0054 required built-in configuration missing: {item.strip()}")
    hp = kernel / "include/linux/lisa_fault_capture.h"
    if hp.exists():
        raise RuntimeError("Candidate0054 capture header already exists; refusing a double patch")
    fp = kernel / "arch/arm64/mm/fault.c"
    mp = kernel / "drivers/mtd/mtdoops.c"
    lp = kernel / "kernel/module.c"
    f, m, modules = fp.read_text(), mp.read_text(), lp.read_text()
    if "LISA0053_ARM64_FAULT" in f or "LISA0054_RAW_FAULT" in f:
        raise RuntimeError("Candidate0054 expects the unmodified fault.c from the pinned source")
    declaration = "static void die_kernel_fault(const char *msg, unsigned long addr,"
    f = once(f, declaration, FAULT_HELPER + declaration, "fault-helper insertion")
    pattern = r"(static void die_kernel_fault\([^{}]+\)\n\{\n)(\tbust_spinlocks\(1\);)"
    f, count = re.subn(pattern,
        r"\1\tlisa_arm64_capture_first_fault(addr, esr, regs);\n\n\2", f)
    if count != 1:
        raise RuntimeError(f"Candidate0054 fault-entry anchor count={count}")
    for inc in ("#include <linux/atomic.h>", "#include <linux/kernel.h>",
                "#include <linux/printk.h>", "#include <linux/lisa_fault_capture.h>",
                "#include <asm/sections.h>"):
        if inc not in f:
            f = once(f, "#include <linux/acpi.h>\n",
                     "#include <linux/acpi.h>\n" + inc + "\n", "fault include")
    m = once(m, "#include <linux/module.h>\n",
             "#include <linux/module.h>\n#include <linux/lisa_fault_capture.h>\n", "mtd include")
    m = once(m, MTD_OLD, MTD_NEW, "bounded mtd tail append")
    modules = once(modules, "\ttrace_module_load(mod);\n", MODULE_MAP, "module relocation map")
    # Do not write partially patched sources until every anchor passed.
    hp.write_text(HEADER)
    fp.write_text(f)
    mp.write_text(m)
    lp.write_text(modules)
    (root / "candidate-0054-arm64-fault-frontload.txt").write_text(
        "evidence=lisa-live-20261004-012226: Candidate0053 runtime markers present; NULL fault at 01:23:21.598; no symbolic fault marker; five snapshots persisted after the fault line\n"
        "artifact0053=boot SHA256 d52b65ac0dbd9c6e8c23766237eae072e0d399b4739d95a08b46121b6b892366; marker and its printk call confirmed in Image\n"
        "uncertainty=last printed line does not prove the printk call returned or identify the faulting driver\n"
        "mutation=publish raw registers before printk; numeric deferred first line; append latch to bounded existing mtdoops records; log module relocation ranges before init\n"
        "unchanged=PAS15 behavior, CFI, panic policy, timers, watchdog, camera, display and proc_create compatibility\n"
        "fault_context=atomic claim and fixed storage; no allocation, filesystem I/O, sleeping lock or task dereference\n"
        "persistence_limit=requires the existing mtdoops worker and storage path to remain runnable; RAM latch alone does not survive power loss\n"
        "CANDIDATE_0054_ARM64_FAULT_FRONTLOAD_GATE=PASS\n"
    )


def verify(root: Path) -> None:
    f = (root / "kernel/arch/arm64/mm/fault.c").read_text()
    m = (root / "kernel/drivers/mtd/mtdoops.c").read_text()
    modules = (root / "kernel/kernel/module.c").read_text()
    body = f[f.index("static void die_kernel_fault("):]
    if body.index("lisa_arm64_capture_first_fault(addr, esr, regs);") > body.index("bust_spinlocks(1);"):
        raise RuntimeError("Raw latch is not first in the fatal fault path")
    helper = f[f.index("static void lisa_arm64_capture_first_fault("):f.index("static void die_kernel_fault(")]
    if helper.index("smp_store_release") > helper.index("printk_deferred(KERN_EMERG"):
        raise RuntimeError("Raw fault is not published before output")
    if "current->" in helper or "show_regs(regs);" in helper:
        raise RuntimeError("First capture unexpectedly depends on task fields or backtrace")
    # Inspect actual format literals, not explanatory comments containing %pS.
    for fmt in re.findall(r'"([^"\n]*(?:\\.[^"\n]*)*)"', helper):
        if "%pS" in fmt or "%ps" in fmt or "%s" in fmt:
            raise RuntimeError("Symbol/string lookup in the first-fault format")
    for token in ("lisa_arm64_fault_copy(lisa_fault_text,", "MTDOOPS_FAST_TAIL_BYTES - lisa_fault_len",
                  "len = lisa_keep + lisa_fault_len;", "write_len = MTDOOPS_HEADER_SIZE + 8 + len;"):
        if token not in m:
            raise RuntimeError(f"Missing bounded persistent-fault gate: {token}")
    if "LISA0054_MODULE name=%s" not in modules:
        raise RuntimeError("Module relocation logging missing")
    image = (root / "candidate-0054-Image").read_bytes()
    for token in (b"LISA0054_RAW_FAULT saved=1", b"LISA0054_MODULE name=%s"):
        if token not in image:
            raise RuntimeError(f"Final Image missing compiled diagnostic: {token!r}")
    sm = (root / "kernel/out/System.map").read_text()
    if not re.search(r"\b[Tt] lisa_arm64_fault_copy(?:[.][A-Za-z0-9_]+)*(?:\n|$)", sm):
        raise RuntimeError("lisa_arm64_fault_copy was not linked into Image")
    cfg = (root / "candidate-0054.ikconfig").read_text()
    for token in ("CONFIG_CFI_CLANG=y\n", "# CONFIG_CFI_PERMISSIVE is not set\n", "CONFIG_MTD_OOPS=y\n"):
        if token not in cfg:
            raise RuntimeError(f"Protection/configuration changed: {token.strip()}")
    print("LISA_CANDIDATE_0054_RAW_LATCH_COMPILED_GATE=PASS", flush=True)
