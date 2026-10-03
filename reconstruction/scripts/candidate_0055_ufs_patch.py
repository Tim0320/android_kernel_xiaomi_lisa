"""Restore the UFS LUN0 -> built-in mi-memory registry after the 302 overlay.

Keep exported signatures and struct layouts unchanged. This is not a UFS
power/clock/firmware change. Keep Candidate0054's raw fault instrumentation.
"""
from pathlib import Path
import hashlib
import difflib
import re
import struct
import types

CAPTURE_PARENT_SHA = "e39b7f9a992f41cf5277928f0ecf488635911b96"
EXPECTED_CRCS = {
    "get_ufs_sdev_data": "0xc5bbd8a8", "get_ufs_hba_data": "0xc40eabac",
    "ufs_read_desc_param": "0x16548413", "get_ufs_data": "0xfa507f92",
    "ufs_get_string_desc": "0x479d5ded", "ufshcd_read_desc": "0xa93e3b58",
    "memblock_mem_size_in_gb": "0x84fd4cc1",
}
UFS_ANCHOR = "/**\n * ufshcd_slave_configure - adjust SCSI device configurations"
DECL = """#if IS_ENABLED(CONFIG_MI_MEMORY_SYSFS)
/* mem_interface.o is built-in even when mi_memory.ko is modular. */
extern void set_ufs_hba_data(struct scsi_device *sdev);
#endif

"""
CONFIGURE_OLD = """static int ufshcd_slave_configure(struct scsi_device *sdev)
{
	struct request_queue *q = sdev->request_queue;
	struct ufs_hba *hba = shost_priv(sdev->host);

	blk_queue_update_dma_pad(q, PRDT_DATA_BYTE_COUNT_PAD - 1);

	ufshcd_crypto_setup_rq_keyslot_manager(hba, q);

	if (ufshcd_is_rpm_autosuspend_allowed(hba))
		sdev->rpm_autosuspend = 1;

	return 0;
}
"""
HOOK = """#if IS_ENABLED(CONFIG_MI_MEMORY_SYSFS)
	/* Publish LUN0 before userspace can read the stock mi_memory proc node. */
	if (sdev->lun == 0)
		set_ufs_hba_data(sdev);
#endif

"""
CONFIGURE_NEW = CONFIGURE_OLD.replace("\treturn 0;\n}", HOOK + "\treturn 0;\n}")
REGISTRY = r'''/* Fixed lifetime matches the built-in provider on this single-UFS phone.
 * Do not publish the pointer until both fields are initialized. No allocation
 * can fail between successful LUN0 configuration and the first proc read.
 */
static struct ufs_data lisa_ufs_registry;
static struct ufs_data *ufs_data_ptr;
static DEFINE_SPINLOCK(lisa_ufs_registry_lock);

noinline void set_ufs_hba_data(struct scsi_device *sdev)
{
	unsigned long flags;
	bool published = false;

	if (!sdev || !sdev->host || sdev->lun != 0)
		return;

	spin_lock_irqsave(&lisa_ufs_registry_lock, flags);
	if (!ufs_data_ptr) {
		lisa_ufs_registry.sdev = sdev;
		lisa_ufs_registry.hba = shost_priv(sdev->host);
		smp_store_release(&ufs_data_ptr, &lisa_ufs_registry);
		published = true;
	}
	spin_unlock_irqrestore(&lisa_ufs_registry_lock, flags);

	if (published)
		pr_info("LISA0055_UFS_REGISTRY stage=bind lun=0 ready=1 host=%d\n", sdev->host->host_no);
}

struct ufs_hba *get_ufs_hba_data(void)
{
	struct ufs_data *data = smp_load_acquire(&ufs_data_ptr);

	if (!data) {
		pr_warn_ratelimited("LISA0055_UFS_REGISTRY stage=hba_read ready=0\n");
		return NULL;
	}
	pr_info_once("LISA0055_UFS_REGISTRY stage=first_hba_read ready=1\n");
	return data->hba;
}
EXPORT_SYMBOL(get_ufs_hba_data);

struct scsi_device *get_ufs_sdev_data(void)
{
	struct ufs_data *data = smp_load_acquire(&ufs_data_ptr);

	return data ? data->sdev : NULL;
}
EXPORT_SYMBOL(get_ufs_sdev_data);

struct ufs_data *get_ufs_data(void)
{
	return smp_load_acquire(&ufs_data_ptr);
}
EXPORT_SYMBOL(get_ufs_data);

void ufsdbg_set_err_state(char *err_reason)
{
	struct ufs_data *data = smp_load_acquire(&ufs_data_ptr);
	int offset = 9;

	if (!data || !err_reason)
		return;
	data->ufs_err_state.err_occurred++;
#ifdef CONFIG_DEBUG_FS
	if (!data->hba->debugfs_files.err_occurred &&
	    data->ufs_err_state.err_occurred > 0)
		data->hba->debugfs_files.err_occurred = true;
#endif
	while (offset) {
		memcpy(data->ufs_err_state.err_reason + offset,
		       data->ufs_err_state.err_reason + offset - 1, 32);
		offset--;
	}
	memcpy(data->ufs_err_state.err_reason, err_reason, 32);
	dump_stack();
}

'''



def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"Candidate0055 {label}: anchor count={text.count(old)}")
    return text.replace(old, new, 1)


def patch_sources(ufs: str, provider: str) -> tuple[str, str]:
    if "LISA0055_UFS_REGISTRY" in provider or "set_ufs_hba_data(sdev);" in ufs:
        raise RuntimeError("Candidate0055 expects the pinned unmodified overlay, not a double patch")
    ufs = once(ufs, UFS_ANCHOR, DECL + UFS_ANCHOR, "UFS declaration")
    ufs = once(ufs, CONFIGURE_OLD, CONFIGURE_NEW, "LUN0 configure hook")
    start = provider.index("static struct ufs_data *ufs_data_ptr;")
    end = provider.index("/*obtain ddr size*/", start)
    old = provider[start:end]
    for token in ("void set_ufs_hba_data(", "return ufs_data_ptr->hba;",
                  "return ufs_data_ptr->sdev;", "void ufsdbg_set_err_state("):
        if token not in old:
            raise RuntimeError(f"Unexpected parent registry implementation: {token}")
    provider = provider[:start] + REGISTRY + provider[end:]
    provider = once(provider, "#include <linux/kernel.h>\n",
                    "#include <linux/kernel.h>\n#include <linux/spinlock.h>\n", "spinlock include")
    # Stock module callers do not all check a NULL HBA. Preserve their exported
    # error-returning descriptor interfaces, rather than moving the same NULL
    # dereference from the getter into hba->dev in a query wrapper.
    for name in ("ufshcd_read_desc", "ufs_get_string_desc", "ufs_read_desc_param"):
        start = provider.index("int " + name + "(")
        end = provider.index("\n}\n", start) + 3
        fn = provider[start:end]
        needle = "\tpm_runtime_get_sync(hba->dev);"
        guard = "\tif (!hba)\n\t\treturn -ENODEV;\n\tif (!buf)\n\t\treturn -EINVAL;\n\n"
        if name == "ufs_get_string_desc":
            # Guard before allocation so the unavailable-HBA path cannot leak.
            needle = "\tdesc_buf = kzalloc(QUERY_DESC_MAX_SIZE, GFP_ATOMIC);"
        fn = once(fn, needle, guard + needle, name + " missing-HBA guard")
        provider = provider[:start] + fn + provider[end:]
    return ufs, provider


def capture_module(root: Path):
    path = root / "reconstruction/scripts/candidate_0054_fault_patch.py"
    data = path.read_bytes()
    if blob_sha(data) != CAPTURE_PARENT_SHA:
        raise RuntimeError("Pinned Candidate0054 raw-fault implementation changed")
    mod = types.ModuleType("candidate0055_retained_capture")
    mod.__file__ = str(path)
    exec(compile(data.decode().replace("0054", "0055"), str(path), "exec"), mod.__dict__)
    return mod


def apply(root: Path, kernel: Path) -> None:
    cfg = (kernel / "out/.config").read_text()
    if "CONFIG_MI_MEMORY_SYSFS=m\n" not in cfg or "CONFIG_SCSI_UFSHCD=y\n" not in cfg:
        raise RuntimeError("Candidate0055 requires the measured modular-mi_memory/built-in-UFS configuration")
    up = kernel / "drivers/scsi/ufs/ufshcd.c"
    pp = kernel / "drivers/misc/mi-memory/mem_interface.c"
    old_ufs, old_provider = up.read_text(), pp.read_text()
    new_ufs, new_provider = patch_sources(old_ufs, old_provider)
    capture_module(root).apply(root, kernel)
    up.write_text(new_ufs)
    pp.write_text(new_provider)
    patch = "".join(difflib.unified_diff(old_ufs.splitlines(True), new_ufs.splitlines(True),
                      fromfile="a/drivers/scsi/ufs/ufshcd.c", tofile="b/drivers/scsi/ufs/ufshcd.c"))
    patch += "".join(difflib.unified_diff(old_provider.splitlines(True), new_provider.splitlines(True),
                      fromfile="a/drivers/misc/mi-memory/mem_interface.c", tofile="b/drivers/misc/mi-memory/mem_interface.c"))
    (root / "candidate-0055-ufs-bridge.patch").write_text(patch)
    (root / "candidate-0055-ufs-registry.txt").write_text(
        "evidence=lisa-live-20261004-020018: MI_RIC pc=get_ufs_hba_data+0x8; lr=mv_proc_show+0x40 [mi_memory]; FAR=0\n"
        "root_gap=known-good-302 ufshcd overlay lacks Xiaomi set_ufs_hba_data LUN0 hook; legacy bootstrap ifdef also excludes CONFIG_MI_MEMORY_SYSFS=m\n"
        "repair=restore LUN0 configure hook using IS_ENABLED; fully initialize fixed registry before release publication; acquire readers; missing-HBA descriptor calls return ENODEV\n"
        "retained=CFI/raw fault latch/PAS/audio/power/watchdog/camera/display/proc_create ABI\n"
        "layout=exported function signatures and struct ufs_data/ufs_hba layouts unchanged\n"
        "runtime_required=stage=bind lun=0 ready=1 before stage=first_hba_read ready=1; MI_RIC proc read must not fault; real descriptor values require device testing\n"
        "CANDIDATE_0055_UFS_REGISTRY_SOURCE_GATE=PASS\n")


def _symbols(path: Path):
    result = []
    for line in path.read_text().splitlines():
        cols = line.split()
        if len(cols) >= 3:
            result.append((int(cols[0], 16), cols[1], cols[2]))
    return result


def verify_linked_hook(image: bytes, symbols) -> int:
    text = next(addr for addr, _, name in symbols if name == "_text")
    targets = {a for a, kind, n in symbols if kind.lower() == 't' and
               re.match(r"^set_ufs_hba_data(?:[.$]|$)", n)}
    callers = {a for a, kind, n in symbols if kind.lower() == 't' and
               re.match(r"^ufshcd_slave_configure(?:[.$]|$)", n)}
    if not targets or not callers:
        raise RuntimeError("Missing linked UFS caller or noinline registry setter")
    boundaries = sorted({a for a, kind, n in symbols if kind.lower() == 't' and not n.startswith('$')})
    hits = 0
    for start in callers:
        end = next((a for a in boundaries if a > start), start)
        for pc in range(start, end, 4):
            off = pc - text
            if off < 0 or off + 4 > len(image):
                continue
            insn = struct.unpack_from('<I', image, off)[0]
            if (insn & 0xfc000000) not in (0x14000000, 0x94000000):
                continue
            imm = insn & 0x03ffffff
            if imm & 0x02000000:
                imm -= 1 << 26
            if pc + (imm << 2) in targets:
                hits += 1
    if not hits:
        raise RuntimeError("LUN0 setter call is not present in compiled ufshcd_slave_configure (possible module-guard regression)")
    return hits


def verify(root: Path) -> None:
    capture_module(root).verify(root)
    ufs = (root / 'kernel/drivers/scsi/ufs/ufshcd.c').read_text()
    provider = (root / 'kernel/drivers/misc/mi-memory/mem_interface.c').read_text()
    if CONFIGURE_NEW not in ufs or DECL not in ufs:
        raise RuntimeError("Modular mi-memory hook source missing")
    if 'smp_store_release(&ufs_data_ptr, &lisa_ufs_registry);' not in provider:
        raise RuntimeError("Registry publication gate missing")
    if provider.count('if (!hba)\n\t\treturn -ENODEV;') != 3:
        raise RuntimeError("Missing descriptor readiness guards")
    cfg = (root / 'candidate-0055.ikconfig').read_text()
    if 'CONFIG_MI_MEMORY_SYSFS=m\n' not in cfg:
        raise RuntimeError("Measured module configuration changed")
    image = (root / 'candidate-0055-Image').read_bytes()
    for token in (b'LISA0055_UFS_REGISTRY stage=bind', b'stage=first_hba_read ready=1'):
        if token not in image:
            raise RuntimeError("Registry runtime marker missing from Image")
    calls = verify_linked_hook(image, _symbols(root / 'kernel/out/System.map'))
    symvers = {p[1]: p[0].lower() for l in (root / 'kernel/out/Module.symvers').read_text().splitlines()
               if len(p := l.split()) >= 2}
    for name, crc in EXPECTED_CRCS.items():
        if symvers.get(name) != crc:
            raise RuntimeError(f"UFS export CRC drift: {name} {symvers.get(name)} != {crc}")
    report = f"linked_lun0_setter_calls={calls}\nufs_provider_crc_matches={len(EXPECTED_CRCS)}/7\nLISA_CANDIDATE_0055_UFS_REGISTRY_COMPILED_GATE=PASS\n"
    (root / 'candidate-0055-ufs-registry-verified.txt').write_text(report)
    print(report, flush=True)
