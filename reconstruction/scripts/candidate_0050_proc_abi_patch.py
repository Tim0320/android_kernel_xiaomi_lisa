#!/usr/bin/env python3
"""Side-effect-free Candidate0050 legacy proc_create ABI bridge.

Extracted from candidate_0050_build.py so later candidates can replay only the
procfs ABI repair without executing the historical Candidate0050 build.
"""
from pathlib import Path


def apply(root: Path, kernel: Path) -> None:
    hp = kernel / "include/linux/proc_fs.h"
    h = hp.read_text()

    old_h = """extern struct proc_dir_entry *proc_create_data_proc_ops(const char *, umode_t,
							struct proc_dir_entry *,
							const struct proc_ops *,
							void *);
#define proc_create_data proc_create_data_proc_ops

struct proc_dir_entry *proc_create(const char *name, umode_t mode, struct proc_dir_entry *parent, const struct proc_ops *proc_ops);
"""
    new_h = """extern struct proc_dir_entry *proc_create_data_proc_ops(const char *, umode_t,
							struct proc_dir_entry *,
							const struct proc_ops *,
							void *);
#define proc_create_data proc_create_data_proc_ops

struct proc_dir_entry *proc_create_proc_ops(const char *name, umode_t mode,
						    struct proc_dir_entry *parent,
						    const struct proc_ops *proc_ops);
#define proc_create proc_create_proc_ops
"""
    if h.count(old_h) != 1:
        raise RuntimeError(f"Candidate0050 proc_create header anchor count={h.count(old_h)}")
    hp.write_text(h.replace(old_h, new_h, 1))

    gp = kernel / "fs/proc/generic.c"
    g = gp.read_text()

    old_current = """struct proc_dir_entry *proc_create(const char *name, umode_t mode,
				   struct proc_dir_entry *parent,
				   const struct proc_ops *proc_ops)
{
	return proc_create_data_proc_ops(name, mode, parent, proc_ops, NULL);
}
EXPORT_SYMBOL(proc_create);

#undef proc_create_data
"""
    new_current = """struct proc_dir_entry *proc_create_proc_ops(const char *name, umode_t mode,
						    struct proc_dir_entry *parent,
						    const struct proc_ops *proc_ops)
{
	return proc_create_data_proc_ops(name, mode, parent, proc_ops, NULL);
}
EXPORT_SYMBOL(proc_create_proc_ops);

#undef proc_create_data
"""
    if g.count(old_current) != 1:
        raise RuntimeError(f"Candidate0050 current proc_create anchor count={g.count(old_current)}")
    g = g.replace(old_current, new_current, 1)

    legacy_data_end = """}
EXPORT_SYMBOL(proc_create_data);
"""
    if g.count(legacy_data_end) != 1:
        raise RuntimeError(
            f"Candidate0050 legacy proc_create_data end count={g.count(legacy_data_end)}"
        )

    legacy_create = r"""
#undef proc_create

struct proc_dir_entry *proc_create(const char *name, umode_t mode,
				   struct proc_dir_entry *parent,
				   const struct file_operations *proc_fops)
{
	pr_info_once("Lisa Candidate 0050: legacy proc_create(file_operations) ABI bridge active\n");
	return proc_create_data(name, mode, parent, proc_fops, NULL);
}
EXPORT_SYMBOL(proc_create);
"""
    g = g.replace(legacy_data_end, legacy_data_end + legacy_create, 1)
    gp.write_text(g)

    hout = hp.read_text()
    gout = gp.read_text()
    gates = [
        ("header current API", "proc_create_proc_ops", hout),
        ("header current macro", "#define proc_create proc_create_proc_ops", hout),
        ("current export", "EXPORT_SYMBOL(proc_create_proc_ops);", gout),
        ("legacy signature", "const struct file_operations *proc_fops)", gout),
        ("legacy export", "EXPORT_SYMBOL(proc_create);", gout),
        ("legacy adapter", "return proc_create_data(name, mode, parent, proc_fops, NULL);", gout),
        (
            "runtime marker",
            "Lisa Candidate 0050: legacy proc_create(file_operations) ABI bridge active",
            gout,
        ),
    ]
    for label, needle, body in gates:
        if needle not in body:
            raise RuntimeError(f"Candidate0050 proc_create ABI gate missing {label}: {needle}")

    (root / "candidate-0050-proc-create-legacy-abi.txt").write_text(
        "runtime_evidence=lisa-live-20261003-205738: sys.boot_completed=1 then NULL dereference 0x400; __cfi_check_fail [mi_memory] -> proc_reg_read -> vfs_read; PID MI_RIC\n"
        "stock_api=exact HyperOS proc_fs.h declares proc_create(... const struct file_operations *)\n"
        "donor_api=current reconstructed core declares proc_create(... const struct proc_ops *)\n"
        "prior_gap=Candidate0046 adapted legacy proc_create_data only; exported proc_create still consumed proc_ops\n"
        "failure_mechanism=stock mi_memory file_operations pointer stored as proc_ops; proc_reg_read reads wrong callback slot and reaches invalid 0x400 function pointer\n"
        "mutation=current in-tree proc_ops callers use proc_create_proc_ops; exported proc_create restored as legacy file_operations adapter via proc_create_data compatibility path\n"
        "cfi_policy=CFI remains enabled; invalid callback is fixed rather than bypassed\n"
        "expected_runtime=MI_RIC read of mi_memory proc node no longer triggers __cfi_check_fail or Fatal exception\n"
        "CANDIDATE_0050_PROC_CREATE_LEGACY_ABI_GATE=PASS\n"
    )
