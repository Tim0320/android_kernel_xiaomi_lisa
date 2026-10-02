#!/usr/bin/env python3
from pathlib import Path
import hashlib
import os
import re
import struct
import subprocess
import sys
import shutil

ROOT=Path(__file__).resolve().parents[2]
KERNEL=ROOT/"kernel"
GOOD=ROOT/"known-good-302"
GOOD_SHA="46af56554ec50e3ff3752858bf38eaeeb852ca0d"
GOOD_FILES={
    "drivers/block/zram/zram_drv.c":"656fadddb35bec4797a88feebe44b46fd8217af8",
    "drivers/block/zram/zcomp.c":"1a8564a79d8dca27b8462d7fe114d35c183c1a60",
    "drivers/block/zram/zram_drv.h":"f2fd46daa7604583b1c3bebaba86b484bca901c7",
    "drivers/block/zram/zcomp.h":"1806475b919df74d6d4f8ce4c611fd486cc0c6c0",
    "drivers/misc/qseecom.c":"e53b0d96e6a0dafa80228c9cf1b424bacb54cba8",
    "drivers/firmware/qcom_scm.c":"96b71bc4cd990f11cfc01ce71952f860f4b049c9",
    "drivers/soc/qcom/smcinvoke.c":"053da831972c512a73d2bd54063cc324234784c1",
    "drivers/scsi/ufs/ufshcd.c":"faca66be8fd83a9460cf33ae08f770bad354a17e",
    "drivers/scsi/ufs/ufs-qcom.c":"562ac279de3978bdb627eb78e29d7549d7f49a2e",
}
SAME_ANCHORS=[
    "drivers/firmware/qcom_scm-smc.c",
    "drivers/firmware/qcom_scm.h",
    "drivers/firmware/qtee_shmbridge.c",
    "drivers/interconnect/qcom/yupik.c",
]
OUT=KERNEL/"out"
SOURCE_SHA="6e568aabc77a06fa787baec1d9e60e4b559874a3"
KNOWN_IMAGE_SHA="492b0b3910d1425cf434ec946851de73d40003f14adb29e695403bf5b60c2b55"
TARGET_RELEASE=b"5.4.289-qgki-g5987d69e25da"
STOCK_BOOT=ROOT/"reconstruction/stock/stock-Image/boot.img"
STOCK_BOOT_SHA="e6f8c978c2cf0a9473d0ac73cdcf3ffb14747246fdc47f82245c43221eb4cbf1"
STOCK_BOOT_BYTES=201326592
STOCK_KERNEL_SIZE=51436032
STOCK_RAMDISK_SIZE=19883180
STOCK_RAMDISK_SHA="0dc218f3167e560444634a6a8cf969eb4470bcf452837a3e23bf45ea0a6819ae"

def sh(cmd, cwd=None, env=None):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, env=env, check=True)

def sha256(data):
    if isinstance(data, Path):
        h=hashlib.sha256()
        with data.open("rb") as f:
            for chunk in iter(lambda:f.read(1024*1024), b""):
                h.update(chunk)
        return h.hexdigest()
    return hashlib.sha256(data).hexdigest()

def align(v,a):
    return (v+a-1)//a*a


def git_blob_sha(path):
    data=Path(path).read_bytes()
    h=hashlib.sha1()
    h.update(b"blob "+str(len(data)).encode()+b"\x00"+data)
    return h.hexdigest()

def overlay_known_good():
    if subprocess.check_output(["git","-C",str(GOOD),"rev-parse","HEAD"], text=True).strip() != GOOD_SHA:
        raise SystemExit("known-good 5.4.302 source SHA mismatch")

    anchor_lines=[]
    for rel in SAME_ANCHORS:
        donor=git_blob_sha(KERNEL/rel)
        good=git_blob_sha(GOOD/rel)
        anchor_lines.append(f"same_anchor {rel} donor={donor} good={good}")
        if donor != good:
            raise SystemExit(f"expected identical known-good anchor differs: {rel}")

    overlay_lines=[]
    for rel, expected in GOOD_FILES.items():
        src=GOOD/rel
        dst=KERNEL/rel
        got=git_blob_sha(src)
        if got != expected:
            raise SystemExit(f"known-good blob mismatch {rel}: {got} != {expected}")
        before=git_blob_sha(dst)
        if before == got:
            raise SystemExit(f"overlay unexpectedly already identical: {rel}")
        shutil.copy2(src,dst)
        after=git_blob_sha(dst)
        if after != expected:
            raise SystemExit(f"overlay copy verification failed: {rel}")
        overlay_lines.append(f"overlay {rel} donor={before} good302={after}")

    (ROOT/"candidate-0046-overlay.txt").write_text(
        f"known_good_repo=LineageOS/android_kernel_xiaomi_sm8350\\n"
        f"known_good_sha={GOOD_SHA}\\n"
        "runtime_oracle=dmesg_TW known-good recovery: QSEE 0x1402000, qnoc 1700000 registered, UFS Gear3/WB, Run /init\\n"
        + "\\n".join(anchor_lines+overlay_lines) + "\\n"
    )


def patch_stock_rwsem():
    p=KERNEL/"include/linux/rwsem.h"
    s=p.read_text()
    if "ANDROID_VENDOR_DATA(1);" in s:
        raise SystemExit("rwsem vendor reserve unexpectedly already present")

    include_old="#ifdef CONFIG_RWSEM_SPIN_ON_OWNER\n#include <linux/osq_lock.h>\n#endif\n"
    include_new=include_old+"#include <linux/android_vendor.h>\n"
    if include_old not in s:
        raise SystemExit("rwsem include insertion point not found")
    s=s.replace(include_old,include_new,1)

    struct_old="#ifdef CONFIG_DEBUG_LOCK_ALLOC\n\tstruct lockdep_map\tdep_map;\n#endif\n};"
    struct_new="#ifdef CONFIG_DEBUG_LOCK_ALLOC\n\tstruct lockdep_map\tdep_map;\n#endif\n\tANDROID_VENDOR_DATA(1);\n};"
    if struct_old not in s:
        raise SystemExit("rwsem struct insertion point not found")
    s=s.replace(struct_old,struct_new,1)
    p.write_text(s)

    out=p.read_text()
    if out.count("ANDROID_VENDOR_DATA(1);") != 1:
        raise SystemExit("rwsem stock reserve verification failed")
    if "#include <linux/android_vendor.h>" not in out:
        raise SystemExit("rwsem android_vendor include verification failed")

    (ROOT/"candidate-0046-layout.txt").write_text(
        "evidence=stock IKHEADERS vs reconstructed runtime layout\n"
        "stock_rw_semaphore_bytes=48\n"
        "candidate_0022_rw_semaphore_bytes=40\n"
        "mutation=restore ANDROID_VENDOR_DATA(1) in struct rw_semaphore\n"
        "expected_inode_i_private_offset_stock=640\n"
        "candidate_0022_inode_i_private_offset=624\n"
        "expected_drm_panel_bytes_stock=104\n"
        "candidate_0022_drm_panel_bytes=96\n"
        "runtime_target=stock msm_drm.ko structural ABI\n"
        "CANDIDATE_0046_RWSEM_LAYOUT_GATE=PASS\n"
    )



def patch_block2mtd_devpath():
    p=KERNEL/"init/do_mounts.c"
    s=p.read_text()
    old=(
        "#ifdef CONFIG_BOARD_XIAOMI\n"
        "\tif (strnstr(name, \"block\", strlen(name)))\n"
        "\t\tname += 6;\n"
        "#endif\n"
    )
    new=(
        "#if defined(CONFIG_BOARD_XIAOMI) || defined(CONFIG_BOARD_XIAOMI_LISA)\n"
        "\t/* Lisa stock cmdline uses /dev/block/sda17 for block2mtd. */\n"
        "\tif (strnstr(name, \"block\", strlen(name)))\n"
        "\t\tname += 6;\n"
        "#endif\n"
    )
    if s.count(old) != 1:
        raise SystemExit(f"name_to_dev_t Xiaomi /dev/block anchor count={s.count(old)}")
    s=s.replace(old,new,1)
    p.write_text(s)

    out=p.read_text()
    if "defined(CONFIG_BOARD_XIAOMI_LISA)" not in out:
        raise SystemExit("Lisa /dev/block name_to_dev_t compatibility patch missing")

    (ROOT/"candidate-0046-devpath.txt").write_text(
        "evidence=Candidate0024 CONFIG_BOARD_XIAOMI=n CONFIG_BOARD_XIAOMI_LISA=y\n"
        "cmdline=block2mtd.block2mtd=/dev/block/sda17,2097152\n"
        "source_before=name_to_dev_t strips /dev/block only under CONFIG_BOARD_XIAOMI\n"
        "failure_mode=/dev/block/sda17 becomes block!sda17 and dev_t lookup fails\n"
        "mutation=allow CONFIG_BOARD_XIAOMI_LISA to strip /dev/block prefix\n"
        "expected_block_device=sda17\n"
        "expected_mtd_index=0\n"
        "CANDIDATE_0046_BLOCK2MTD_DEVPATH_GATE=PASS\n"
    )

def patch_mtdoops_persistence():
    p=KERNEL/"drivers/mtd/mtdoops.c"
    s=p.read_text()

    old="#define MTDOOPS_MAX_MTD_SIZE (8 * 1024 * 1024)"
    new="#define MTDOOPS_MAX_MTD_SIZE (16 * 1024 * 1024)"
    if s.count(old) != 1:
        raise SystemExit(f"mtdoops max-size anchor count={s.count(old)}")
    s=s.replace(old,new,1)

    old="cxt->dump.max_reason = KMSG_DUMP_OOPS;"
    new="cxt->dump.max_reason = KMSG_DUMP_POWEROFF;"
    if s.count(old) != 1:
        raise SystemExit(f"mtdoops max_reason anchor count={s.count(old)}")
    s=s.replace(old,new,1)

    old=(
        "\tif (reason != KMSG_DUMP_OOPS) {\n"
        "\t\t/* Panics must be written immediately */\n"
        "\t\tmtdoops_write(cxt, 1);\n"
        "\t} else {\n"
        "\t\t/* For other cases, schedule work to write it \"nicely\" */\n"
        "\t\tschedule_work(&cxt->work_write);\n"
        "\t}\n"
    )
    new=(
        "\tif (reason == KMSG_DUMP_PANIC) {\n"
        "\t\t/* Keep the panic path unchanged. */\n"
        "\t\tmtdoops_write(cxt, 1);\n"
        "\t} else if (reason == KMSG_DUMP_OOPS) {\n"
        "\t\t/* Oops may use the normal deferred write path. */\n"
        "\t\tschedule_work(&cxt->work_write);\n"
        "\t} else {\n"
        "\t\t/* Persist orderly restart/halt/poweroff before PSHOLD. */\n"
        "\t\tmtdoops_write(cxt, 0);\n"
        "\t\tmtd_sync(cxt->mtd);\n"
        "\t}\n"
    )
    if s.count(old) != 1:
        raise SystemExit(f"mtdoops dump-path anchor count={s.count(old)}")
    s=s.replace(old,new,1)

    old="\tfind_next_position(cxt);\n\tprintk(KERN_INFO \"mtdoops: Attached to MTD device %d\\n\", mtd->index);\n"
    new=(
        "\tfind_next_position(cxt);\n"
        "\t/* Ensure a full historical ring has a writable slot. */\n"
        "\tflush_work(&cxt->work_erase);\n"
        "\tprintk(KERN_INFO \"mtdoops: Lisa Candidate 0046 logger ready, pages=%d record=%lu\\n\", "
        "cxt->oops_pages, record_size);\n"
        "\tprintk(KERN_INFO \"mtdoops: Attached to MTD device %d\\n\", mtd->index);\n"
    )
    if s.count(old) != 1:
        raise SystemExit(f"mtdoops attach anchor count={s.count(old)}")
    s=s.replace(old,new,1)
    p.write_text(s)

    out=p.read_text()
    gates=[
        "#define MTDOOPS_MAX_MTD_SIZE (16 * 1024 * 1024)",
        "cxt->dump.max_reason = KMSG_DUMP_POWEROFF;",
        "mtd_sync(cxt->mtd);",
        "Lisa Candidate 0046 logger ready",
    ]
    for g in gates:
        if g not in out:
            raise SystemExit(f"mtdoops persistence gate missing: {g}")

    (ROOT/"candidate-0046-logging.txt").write_text(
        "evidence=iter0008/iter0009 oops unchanged across failed boots\n"
        "oops_partition_bytes=16777216\n"
        "source_mtdoops_limit_before=8388608\n"
        "mutation=allow 16MiB oops + persist restart/halt/poweroff kmsg + sync\n"
        "record_size_cmdline=2097152\n"
        "expected_records=8\n"
        "CANDIDATE_0046_PERSISTENT_KMSG_GATE=PASS\n"
    )


def patch_mtdoops_periodic_snapshot():
    p=KERNEL/"drivers/mtd/mtdoops.c"
    s=p.read_text()

    old=(
        "\tstruct work_struct work_erase;\n"
        "\tstruct work_struct work_write;\n"
        "\tstruct mtd_info *mtd;\n"
    )
    new=(
        "\tstruct work_struct work_erase;\n"
        "\tstruct work_struct work_write;\n"
        "\tstruct delayed_work work_snapshot;\n"
        "\tstruct kmsg_dumper snapshot_dump;\n"
        "\tunsigned int snapshot_seq;\n"
        "\tstruct mtd_info *mtd;\n"
    )
    if s.count(old) != 1:
        raise SystemExit(f"mtdoops context work anchor count={s.count(old)}")
    s=s.replace(old,new,1)

    old=(
        "static void mtdoops_workfunc_write(struct work_struct *work)\n"
        "{\n"
        "\tstruct mtdoops_context *cxt =\n"
        "\t\t\tcontainer_of(work, struct mtdoops_context, work_write);\n"
        "\n"
        "\tmtdoops_write(cxt, 0);\n"
        "}\n"
    )
    new=old + (
        "\n"
        "#define MTDOOPS_SNAPSHOT_FIRST_DELAY (2 * HZ)\n"
        "#define MTDOOPS_SNAPSHOT_INTERVAL    msecs_to_jiffies(10)\n"
        "\n"
        "static void mtdoops_snapshot_workfunc(struct work_struct *work)\n"
        "{\n"
        "\tstruct delayed_work *dwork = to_delayed_work(work);\n"
        "\tstruct mtdoops_context *cxt =\n"
        "\t\tcontainer_of(dwork, struct mtdoops_context, work_snapshot);\n"
        "\tsize_t len = 0;\n"
        "\tbool got;\n"
        "\n"
        "\tif (!cxt->mtd)\n"
        "\t\treturn;\n"
        "\n"
        "\t/* Keep the next ring slot writable before taking a snapshot. */\n"
        "\tflush_work(&cxt->work_erase);\n"
        "\tmemset(cxt->oops_buf, 0xff, record_size);\n"
        "\n"
        "\t/* Use a private, unregistered dumper so normal panic/oops dumping\n"
        "\t * cannot race with the diagnostic snapshot iterator state.\n"
        "\t */\n"
        "\tcxt->snapshot_dump.active = true;\n"
        "\tkmsg_dump_rewind(&cxt->snapshot_dump);\n"
        "\tgot = kmsg_dump_get_buffer(&cxt->snapshot_dump, true,\n"
        "\t\t\tcxt->oops_buf + MTDOOPS_HEADER_SIZE,\n"
        "\t\t\trecord_size - MTDOOPS_HEADER_SIZE, &len);\n"
        "\tcxt->snapshot_dump.active = false;\n"
        "\n"
        "\tif (got && len) {\n"
        "\t\tmtdoops_write(cxt, 0);\n"
        "\t\tmtd_sync(cxt->mtd);\n"
        "\t\tcxt->snapshot_seq++;\n"
        "\t\tprintk(KERN_INFO \"mtdoops: Lisa Candidate 0046 snapshot %u persisted (%zu bytes)\\n\",\n"
        "\t\t       cxt->snapshot_seq, len);\n"
        "\t}\n"
        "\n"
        "\tif (cxt->mtd)\n"
        "\t\tschedule_delayed_work(&cxt->work_snapshot,\n"
        "\t\t\t\t      MTDOOPS_SNAPSHOT_INTERVAL);\n"
        "}\n"
    )
    if s.count(old) != 1:
        raise SystemExit(f"mtdoops writer function anchor count={s.count(old)}")
    s=s.replace(old,new,1)

    old=(
        "\tprintk(KERN_INFO \"mtdoops: Attached to MTD device %d\\n\", mtd->index);\n"
        "}\n"
    )
    new=(
        "\tprintk(KERN_INFO \"mtdoops: Attached to MTD device %d\\n\", mtd->index);\n"
        "\tschedule_delayed_work(&cxt->work_snapshot,\n"
        "\t\t\t      MTDOOPS_SNAPSHOT_FIRST_DELAY);\n"
        "}\n"
    )
    if s.count(old) != 1:
        raise SystemExit(f"mtdoops notify-add schedule anchor count={s.count(old)}")
    s=s.replace(old,new,1)

    old=(
        "\tif (kmsg_dump_unregister(&cxt->dump) < 0)\n"
        "\t\tprintk(KERN_WARNING \"mtdoops: could not unregister kmsg_dumper\\n\");\n"
        "\n"
        "\tcxt->mtd = NULL;\n"
    )
    new=(
        "\tcancel_delayed_work_sync(&cxt->work_snapshot);\n"
        "\tif (kmsg_dump_unregister(&cxt->dump) < 0)\n"
        "\t\tprintk(KERN_WARNING \"mtdoops: could not unregister kmsg_dumper\\n\");\n"
        "\n"
        "\tcxt->mtd = NULL;\n"
    )
    if s.count(old) != 1:
        raise SystemExit(f"mtdoops notify-remove anchor count={s.count(old)}")
    s=s.replace(old,new,1)

    old=(
        "\tINIT_WORK(&cxt->work_erase, mtdoops_workfunc_erase);\n"
        "\tINIT_WORK(&cxt->work_write, mtdoops_workfunc_write);\n"
        "\n"
        "\tregister_mtd_user(&mtdoops_notifier);\n"
    )
    new=(
        "\tINIT_WORK(&cxt->work_erase, mtdoops_workfunc_erase);\n"
        "\tINIT_WORK(&cxt->work_write, mtdoops_workfunc_write);\n"
        "\tINIT_DELAYED_WORK(&cxt->work_snapshot, mtdoops_snapshot_workfunc);\n"
        "\tcxt->snapshot_seq = 0;\n"
        "\n"
        "\tregister_mtd_user(&mtdoops_notifier);\n"
    )
    if s.count(old) != 1:
        raise SystemExit(f"mtdoops init-work anchor count={s.count(old)}")
    s=s.replace(old,new,1)

    p.write_text(s)
    out=p.read_text()
    gates=[
        "struct delayed_work work_snapshot;",
        "struct kmsg_dumper snapshot_dump;",
        "MTDOOPS_SNAPSHOT_FIRST_DELAY (2 * HZ)",
        "MTDOOPS_SNAPSHOT_INTERVAL    msecs_to_jiffies(10)",
        "kmsg_dump_rewind(&cxt->snapshot_dump);",
        "Lisa Candidate 0046 snapshot %u persisted",
        "INIT_DELAYED_WORK(&cxt->work_snapshot, mtdoops_snapshot_workfunc);",
        "schedule_delayed_work(&cxt->work_snapshot",
    ]
    for g in gates:
        if g not in out:
            raise SystemExit(f"periodic snapshot gate missing: {g}")

    (ROOT/"candidate-0046-snapshot.txt").write_text(
        "evidence=Candidate0025 oops SHA unchanged despite block2mtd devpath fix\n"
        "reset_mode=PSHOLD hard reset may bypass kmsg_dump callbacks\n"
        "mutation=private kmsg_dumper periodic snapshots to mtdoops ring\n"
        "first_snapshot_delay_seconds=2\n"
        "snapshot_interval_milliseconds=10\n"
        "record_size_bytes=2097152\n"
        "ring_records=8\n"
        "history_window_seconds_approx=1\n"
        "CANDIDATE_0046_PERIODIC_KMSG_GATE=PASS\n"
    )



def patch_mtdoops_fast_snapshot_io():
    p=KERNEL/"drivers/mtd/mtdoops.c"
    s=p.read_text()

    anchor="static void mtdoops_snapshot_workfunc(struct work_struct *work)\n"
    if s.count(anchor) != 1:
        raise SystemExit(f"fast-tail workfunc anchor count={s.count(anchor)}")

    helper=(
        "#define MTDOOPS_FAST_TAIL_MAGIC 0x3146544cU\n"
        "#define MTDOOPS_FAST_TAIL_BYTES (4 * 1024)\n"
        "\n"
        "static void mtdoops_snapshot_write_fast(struct mtdoops_context *cxt, size_t len)\n"
        "{\n"
        "\tstruct mtd_info *mtd = cxt->mtd;\n"
        "\tsize_t retlen = 0;\n"
        "\tsize_t write_len = MTDOOPS_HEADER_SIZE + 8 + len;\n"
        "\tu32 *hdr = cxt->oops_buf;\n"
        "\tu32 *meta = (u32 *)(cxt->oops_buf + MTDOOPS_HEADER_SIZE);\n"
        "\tint ret;\n"
        "\n"
        "\t/* This fast path is safe only for the block2mtd RAM-like backend. */\n"
        "\tif (mtd->type != MTD_RAM || mtd->writesize != 1) {\n"
        "\t\tmtdoops_write(cxt, 0);\n"
        "\t\tmtd_sync(mtd);\n"
        "\t\treturn;\n"
        "\t}\n"
        "\n"
        "\thdr[0] = cxt->nextcount;\n"
        "\thdr[1] = MTDOOPS_KERNMSG_MAGIC;\n"
        "\tmeta[0] = MTDOOPS_FAST_TAIL_MAGIC;\n"
        "\tmeta[1] = (u32)len;\n"
        "\n"
        "\tret = mtd_write(mtd, cxt->nextpage * record_size,\n"
        "\t\t\twrite_len, &retlen, cxt->oops_buf);\n"
        "\tif (ret < 0 || retlen != write_len)\n"
        "\t\tprintk(KERN_ERR \"mtdoops: fast-tail write failure at %ld (%td of %zu written), error %d\\n\",\n"
        "\t\t       cxt->nextpage * record_size, retlen, write_len, ret);\n"
        "\tmtd_sync(mtd);\n"
        "\tmark_page_used(cxt, cxt->nextpage);\n"
        "\tmemset(cxt->oops_buf, 0xff, write_len);\n"
        "\n"
        "\t/* block2mtd permits direct overwrite, so avoid a 2MiB erase per sample. */\n"
        "\tcxt->nextpage++;\n"
        "\tif (cxt->nextpage >= cxt->oops_pages)\n"
        "\t\tcxt->nextpage = 0;\n"
        "\tcxt->nextcount++;\n"
        "\tif (cxt->nextcount == 0xffffffff)\n"
        "\t\tcxt->nextcount = 0;\n"
        "\tprintk(KERN_DEBUG \"mtdoops: fast ready %d, %d\\n\",\n"
        "\t       cxt->nextpage, cxt->nextcount);\n"
        "}\n"
        "\n"
    )
    s=s.replace(anchor,helper+anchor,1)

    old=(
        "\t/* Keep the next ring slot writable before taking a snapshot. */\n"
        "\tflush_work(&cxt->work_erase);\n"
        "\tmemset(cxt->oops_buf, 0xff, record_size);\n"
    )
    new=(
        "\t/* Fast-tail snapshots overwrite block2mtd directly; no 2MiB erase. */\n"
        "\tmemset(cxt->oops_buf, 0xff, record_size);\n"
    )
    if s.count(old) != 1:
        raise SystemExit(f"fast-tail erase removal anchor count={s.count(old)}")
    s=s.replace(old,new,1)

    old=(
        "\tgot = kmsg_dump_get_buffer(&cxt->snapshot_dump, true,\n"
        "\t\t\tcxt->oops_buf + MTDOOPS_HEADER_SIZE,\n"
        "\t\t\trecord_size - MTDOOPS_HEADER_SIZE, &len);\n"
    )
    new=(
        "\tgot = kmsg_dump_get_buffer(&cxt->snapshot_dump, true,\n"
        "\t\t\tcxt->oops_buf + MTDOOPS_HEADER_SIZE + 8,\n"
        "\t\t\tMTDOOPS_FAST_TAIL_BYTES, &len);\n"
    )
    if s.count(old) != 1:
        raise SystemExit(f"fast-tail kmsg buffer anchor count={s.count(old)}")
    s=s.replace(old,new,1)

    old=(
        "\tif (got && len) {\n"
        "\t\tmtdoops_write(cxt, 0);\n"
        "\t\tmtd_sync(cxt->mtd);\n"
        "\t\tcxt->snapshot_seq++;\n"
    )
    new=(
        "\tif (got && len) {\n"
        "\t\tmtdoops_snapshot_write_fast(cxt, len);\n"
        "\t\tcxt->snapshot_seq++;\n"
    )
    if s.count(old) != 1:
        raise SystemExit(f"fast-tail writer anchor count={s.count(old)}")
    s=s.replace(old,new,1)

    p.write_text(s)
    out=p.read_text()
    gates=[
        "#define MTDOOPS_FAST_TAIL_MAGIC 0x3146544cU",
        "#define MTDOOPS_FAST_TAIL_BYTES (4 * 1024)",
        "mtdoops_snapshot_write_fast(cxt, len);",
        "mtd->type != MTD_RAM || mtd->writesize != 1",
        "block2mtd permits direct overwrite",
        "cxt->oops_buf + MTDOOPS_HEADER_SIZE + 8",
    ]
    for g in gates:
        if g not in out:
            raise SystemExit(f"fast-tail gate missing: {g}")

    (ROOT/"candidate-0046-fast-tail.txt").write_text(
        "backend=block2mtd MTD_RAM writesize=1\n"
        "snapshot_tail_bytes=4096\n"
        "snapshot_record_header_bytes=16\n"
        "write_mode=partial_overwrite_no_2MiB_erase\n"
        "sync_each_snapshot=1\n"
        "normal_panic_oops_path_unchanged=1\n"
        "CANDIDATE_0046_FAST_TAIL_GATE=PASS\n"
    )


def patch_qgki_module_abi():
    stock_root=os.environ.get("STOCK_ABI_ROOT","")
    if not stock_root:
        raise SystemExit("STOCK_ABI_ROOT is required for Candidate 0046")
    if not Path(stock_root).is_dir():
        raise SystemExit(f"stock ABI root missing: {stock_root}")

    # proc_create_data: keep current proc_ops callers, re-export legacy
    # file_operations ABI required by the stock QGKI msm_drm module.
    p=KERNEL/"include/linux/proc_fs.h"
    text=p.read_text()
    old="""extern struct proc_dir_entry *proc_create_data(const char *, umode_t,
					       struct proc_dir_entry *,
					       const struct proc_ops *,
					       void *);
"""
    new="""extern struct proc_dir_entry *proc_create_data_proc_ops(const char *, umode_t,
							struct proc_dir_entry *,
							const struct proc_ops *,
							void *);
#define proc_create_data proc_create_data_proc_ops
"""
    if old not in text:
        raise SystemExit("proc_create_data prototype block not found")
    p.write_text(text.replace(old,new,1))

    p=KERNEL/"fs/proc/internal.h"
    text=p.read_text()
    old="""	const struct inode_operations *proc_iops;
	union {
		const struct proc_ops *proc_ops;
		const struct file_operations *proc_dir_ops;
	};
	const struct dentry_operations *proc_dops;
"""
    new="""	const struct inode_operations *proc_iops;
#ifdef __GENKSYMS__
	const struct file_operations *proc_fops;
#else
	union {
		const struct proc_ops *proc_ops;
		const struct file_operations *proc_dir_ops;
	};
	struct proc_ops legacy_proc_ops;
#endif
	const struct dentry_operations *proc_dops;
"""
    if old not in text:
        raise SystemExit("proc_dir_entry operation block not found")
    p.write_text(text.replace(old,new,1))

    p=KERNEL/"fs/proc/generic.c"
    text=p.read_text()
    old="""struct proc_dir_entry *proc_create_data(const char *name, umode_t mode,
		struct proc_dir_entry *parent,
		const struct proc_ops *proc_ops, void *data)
{
	struct proc_dir_entry *p;

	p = proc_create_reg(name, mode, &parent, data);
	if (!p)
		return NULL;
	p->proc_ops = proc_ops;
	return proc_register(parent, p);
}
EXPORT_SYMBOL(proc_create_data);
 
struct proc_dir_entry *proc_create(const char *name, umode_t mode,
				   struct proc_dir_entry *parent,
				   const struct proc_ops *proc_ops)
{
	return proc_create_data(name, mode, parent, proc_ops, NULL);
}
EXPORT_SYMBOL(proc_create);
"""
    new="""struct proc_dir_entry *proc_create_data_proc_ops(const char *name, umode_t mode,
		struct proc_dir_entry *parent,
		const struct proc_ops *proc_ops, void *data)
{
	struct proc_dir_entry *p;

	p = proc_create_reg(name, mode, &parent, data);
	if (!p)
		return NULL;
	p->proc_ops = proc_ops;
	return proc_register(parent, p);
}
EXPORT_SYMBOL(proc_create_data_proc_ops);

struct proc_dir_entry *proc_create(const char *name, umode_t mode,
				   struct proc_dir_entry *parent,
				   const struct proc_ops *proc_ops)
{
	return proc_create_data_proc_ops(name, mode, parent, proc_ops, NULL);
}
EXPORT_SYMBOL(proc_create);

#undef proc_create_data

struct proc_dir_entry *proc_create_data(const char *name, umode_t mode,
		struct proc_dir_entry *parent,
		const struct file_operations *proc_fops, void *data)
{
	struct proc_dir_entry *p;
	struct proc_ops *ops;

	p = proc_create_reg(name, mode, &parent, data);
	if (!p)
		return NULL;

	ops = &p->legacy_proc_ops;
	if (proc_fops) {
		ops->proc_open = proc_fops->open;
		ops->proc_read = proc_fops->read;
		ops->proc_write = proc_fops->write;
		ops->proc_lseek = proc_fops->llseek;
		ops->proc_release = proc_fops->release;
		ops->proc_poll = proc_fops->poll;
		ops->proc_ioctl = proc_fops->unlocked_ioctl;
#ifdef CONFIG_COMPAT
		ops->proc_compat_ioctl = proc_fops->compat_ioctl;
#endif
		ops->proc_mmap = proc_fops->mmap;
		ops->proc_get_unmapped_area = proc_fops->get_unmapped_area;
	}
	p->proc_ops = ops;
	return proc_register(parent, p);
}
EXPORT_SYMBOL(proc_create_data);
"""
    if old not in text:
        raise SystemExit("proc_create_data implementation block not found")
    p.write_text(text.replace(old,new,1))

    # Exact stock scheduler genksyms view needed by msm_drm imports.
    p=KERNEL/"kernel/sched/sched.h"
    text=p.read_text()
    old="""	u64			exec_clock;
	u64			min_vruntime;
#ifndef CONFIG_64BIT
"""
    new="""	u64			exec_clock;
	u64			min_vruntime;
#if defined(__GENKSYMS__) && defined(CONFIG_PERF_HUMANTASK)
	u64			min_vruntimex;
#endif
#ifndef CONFIG_64BIT
"""
    if old not in text:
        raise SystemExit("scheduler min_vruntime insertion point not found")
    p.write_text(text.replace(old,new,1))

    # Route genksyms only (not normal C compilation) through the stock
    # IKHEADERS tree. This reproduces the stock QGKI exported CRC graph
    # while preserving the reconstructed runtime implementations.
    p=KERNEL/"scripts/Makefile.build"
    text=p.read_text()
    stock=(
        "-I$(STOCK_ABI_ROOT)/arch/$(SRCARCH)/include "
        "-I$(STOCK_ABI_ROOT)/arch/$(SRCARCH)/include/generated "
        "-I$(STOCK_ABI_ROOT)/include "
        "-I$(STOCK_ABI_ROOT)/include/generated "
        "-I$(STOCK_ABI_ROOT)/arch/$(SRCARCH)/include/uapi "
        "-I$(STOCK_ABI_ROOT)/arch/$(SRCARCH)/include/generated/uapi "
        "-I$(STOCK_ABI_ROOT)/include/uapi "
        "-I$(STOCK_ABI_ROOT)/include/generated/uapi"
    )
    conditional=(
        "$(if $(or "
        "$(findstring /lib/zstd/,$<),"
        "$(findstring /drivers/android/vendor_hooks.c,$<)"
        f"),,{stock})"
    )
    lines=text.splitlines(keepends=True)
    c_done=False
    asm_done=False
    for i,line in enumerate(lines):
        if not c_done and "$(CPP) -D__GENKSYMS__ $(c_flags) $< |" in line:
            lines[i]=line.replace(
                "$(CPP) -D__GENKSYMS__",
                f"$(CPP) {conditional} -D__GENKSYMS__",1)
            c_done=True
            continue
        if not asm_done and "$(CPP) -D__GENKSYMS__ $(c_flags) -xc - |" in line:
            lines[i]=line.replace(
                "$(CPP) -D__GENKSYMS__",
                f"$(CPP) {stock} -D__GENKSYMS__",1)
            asm_done=True
    if not c_done or not asm_done:
        raise SystemExit(f"genksyms Makefile routing failed c={c_done} asm={asm_done}")
    p.write_text("".join(lines))

    (ROOT/"candidate-0046-qgki.txt").write_text(
        "root_cause=stock hwkm.ko and msm_drm.ko reject reconstructed module_layout CRC\n"
        "stock_msm_drm_module_layout=0xba39cbb8\n"
        "stock_msm_drm_version_entries=736\n"
        "mutation=legacy proc ABI + scheduler genksyms view + stock IKHEADERS routed to genksyms\n"
        "runtime_rwsem_stock_layout=retained\n"
        "CANDIDATE_0046_QGKI_ABI_PATCH_GATE=PASS\n"
    )


def patch_display_module_mode():
    # Candidate 0027 built Qualcomm/Xiaomi techpack display into the Image
    # because lahainadisp.conf unconditionally exported DISPLAY_BUILD=y.
    # The known-good runtime instead reaches /init without an Image-owned
    # msm_drm and later runs display code as [msm_drm].  Keep the exact
    # display sources/config macros but build msm_drm.o as a module.
    p=KERNEL/"techpack/display/config/lahainadisp.conf"
    text=p.read_text()
    old="export CONFIG_DISPLAY_BUILD=y\n"
    new="export CONFIG_DISPLAY_BUILD=m\n"
    if text.count(old) != 1:
        raise SystemExit(f"DISPLAY_BUILD=y anchor count={text.count(old)}")
    p.write_text(text.replace(old,new,1))

    out=p.read_text()
    if "export CONFIG_DISPLAY_BUILD=m" not in out:
        raise SystemExit("techpack display module-mode patch missing")

    (ROOT/"candidate-0046-display-mode.txt").write_text(
        "runtime_oracle=known-good 5.4.302 reaches Run /init, first-stage msm_drm module mismatch is non-fatal, later display functions are module-owned [msm_drm]\n"
        "candidate_0027_divergence=techpack display initializes before Run /init and later vendor_boot msm_drm.ko collides with duplicate tracepoint export\n"
        "source_control=techpack/display/config/lahainadisp.conf CONFIG_DISPLAY_BUILD\n"
        "before=CONFIG_DISPLAY_BUILD=y\n"
        "after=CONFIG_DISPLAY_BUILD=m\n"
        "expected_image_msm_drm=absent\n"
        "expected_built_module=kernel/out/techpack/display/msm/msm_drm.ko\n"
        "CANDIDATE_0046_DISPLAY_MODULE_MODE_GATE=PASS\n"
    )

def patch_gpu_gpulist():
    p=KERNEL/"drivers/gpu/msm/adreno-gpulist.h"
    text=p.read_text()

    old=(
        "static const struct adreno_gpu_core *adreno_gpulist[] = {\n"
        "\t&adreno_gpu_core_a660.base,\n"
        "\t&adreno_gpu_core_a660v2.base,\n"
        "};\n"
    )
    new=(
        "static const struct adreno_gpu_core *adreno_gpulist[] = {\n"
        "\t&adreno_gpu_core_a660.base,\n"
        "\t&adreno_gpu_core_a660v2.base,\n"
        "\t&adreno_gpu_core_a642.base,\n"
        "\t&adreno_gpu_core_a642l.base,\n"
        "\t&adreno_gpu_core_a643.base,\n"
        "};\n"
    )
    if text.count(old) != 1:
        raise SystemExit(f"Candidate0046 active GPU list anchor count={text.count(old)}")

    # The donor already contains the A642/A642L/A643 definitions; only the
    # selector table was truncated to A660/A660v2.
    for required in [
        "static const struct adreno_a6xx_core adreno_gpu_core_a642 = {",
        "static const struct adreno_a6xx_core adreno_gpu_core_a642l = {",
        "static const struct adreno_a6xx_core adreno_gpu_core_a643 = {",
        '.compatible = "qcom,adreno-gpu-a642l",',
    ]:
        if required not in text:
            raise SystemExit(f"Candidate0046 missing existing GPU definition: {required}")

    text=text.replace(old,new,1)
    p.write_text(text)

    out=p.read_text()
    for required in [
        "&adreno_gpu_core_a642.base,",
        "&adreno_gpu_core_a642l.base,",
        "&adreno_gpu_core_a643.base,",
    ]:
        if out.count(required) != 1:
            raise SystemExit(f"Candidate0046 GPU selector gate failed: {required}")

    dts=(KERNEL/"arch/arm64/boot/dts/vendor/qcom/yupik-gpu.dtsi").read_text()
    if '"qcom,adreno-gpu-a642l"' not in dts:
        raise SystemExit("Candidate0046 Yupik DT does not identify A642L")
    if "qcom,chipid = <0x06030500>;" not in dts:
        raise SystemExit("Candidate0046 Yupik DT chipid is not 0x06030500")

    (ROOT/"candidate-0046-gpu-selector.txt").write_text(
        "evidence=Candidate0045 live ADB log: Unknown GPU chip ID 06030500 -> kgsl master bind -19 -> no /dev/kgsl-3d0 -> SurfaceFlinger crash loop -> reboot,rescueparty\n"
        "device_tree_compatible=qcom,adreno-gpu-a642l\n"
        "device_tree_chipid=0x06030500\n"
        "donor_gpu_definitions=a642,a642l,a643 already present\n"
        "donor_active_list_before=a660,a660v2 only\n"
        "mutation=add a642,a642l,a643 to active adreno_gpulist selector only\n"
        "expected_runtime=/dev/kgsl-3d0 exists and Unknown GPU chip ID 06030500 disappears\n"
        "CANDIDATE_0046_GPU_SELECTOR_GATE=PASS\n"
    )


def patch_yupik():
    p=KERNEL/"drivers/interconnect/qcom/yupik.c"
    s=p.read_text()

    qos_decl="static struct qcom_icc_qosbox qxm_ipa_qos = {"
    qos_offset=".offsets = { 0x10000 },"
    if s.count(qos_decl) != 1:
        raise SystemExit(f"unexpected qxm_ipa_qos declaration count: {s.count(qos_decl)}")
    if s.count(qos_offset) != 1:
        raise SystemExit(f"unexpected qxm_ipa qos offset count: {s.count(qos_offset)}")

    old="\t.qosbox = &qxm_ipa_qos,"
    if s.count(old) != 1:
        raise SystemExit(f"unexpected qxm_ipa qosbox binding count: {s.count(old)}")
    new="\t/* Lisa Candidate 0046 diagnostic: never touch inaccessible IPA QoS MMIO. */\n\t.qosbox = NULL,"
    s=s.replace(old,new,1)

    marker='\tret = clk_bulk_prepare_enable(qp->num_clks, qp->clks);\n'
    if s.count(marker) != 1:
        raise SystemExit(f"unexpected clock-enable marker count: {s.count(marker)}")
    marker_new=marker+'\n\tif (desc == &yupik_aggre2_noc)\n\t\tdev_info(&pdev->dev, "Lisa Candidate 0046: qxm_ipa QoS fully disabled\\n");\n'
    s=s.replace(marker,marker_new,1)
    p.write_text(s)

    out=p.read_text()
    if out.count(".qosbox = NULL,") != 1:
        raise SystemExit("qxm_ipa qosbox disable verification failed")
    if "Lisa Candidate 0046: qxm_ipa QoS fully disabled" not in out:
        raise SystemExit("Candidate 0046 runtime marker missing")

    (ROOT/"candidate-0046-root-cause.txt").write_text(
        "candidate_0019_boot_sha256=ceb2a7a6e4b621cb129f5818f1c6fec245601cd55dfbc756c05e9e888eab4488\n"
        "candidate_0019_exception=synchronous external abort 0x96000010\n"
        "candidate_0019_pc=regmap_mmio_read32le+0x8/0x20\n"
        "candidate_0019_call_path=qcom_icc_set_qos -> qnoc_probe\n"
        "candidate_0019_fault_register_offset=0x10008\n"
        "candidate_0019_aggre2_registration=not reached\n"
        "candidate_0046_control=retain qxm_ipa.qosbox=NULL; overlay known-good 5.4.302 secure/UFS + zram paths\n"
        "companion_base=reconstruction/stock/stock-Image-3.09\n"
    )



def patch_stock_watchdog_timings():
    p=KERNEL/"drivers/soc/qcom/Kconfig"
    x=p.read_text()

    old=(
        "config QCOM_WATCHDOG_BARK_TIME\n"
        "\tdepends on QCOM_WDT_CORE\n"
        "\tint \"Qualcomm Technologies, Inc. Watchdog bark time in ms\"\n"
        "\tdefault 11000\n"
        "\trange 11000 11000\n"
    )
    new=(
        "config QCOM_WATCHDOG_BARK_TIME\n"
        "\tdepends on QCOM_WDT_CORE\n"
        "\tint \"Qualcomm Technologies, Inc. Watchdog bark time in ms\"\n"
        "\tdefault 20000\n"
        "\trange 11000 20000\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"watchdog bark Kconfig anchor count={x.count(old)}")
    x=x.replace(old,new,1)

    old=(
        "config QCOM_WATCHDOG_PET_TIME\n"
        "\tdepends on QCOM_WDT_CORE\n"
        "\tint \"Qualcomm Technologies, Inc. Watchdog pet time in ms\"\n"
        "\tdefault 9360\n"
        "\trange 9360 9360\n"
    )
    new=(
        "config QCOM_WATCHDOG_PET_TIME\n"
        "\tdepends on QCOM_WDT_CORE\n"
        "\tint \"Qualcomm Technologies, Inc. Watchdog pet time in ms\"\n"
        "\tdefault 15000\n"
        "\trange 9360 15000\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"watchdog pet Kconfig anchor count={x.count(old)}")
    x=x.replace(old,new,1)
    p.write_text(x)

    cfg=OUT/".config"
    c=cfg.read_text()
    c=re.sub(r"^CONFIG_QCOM_WATCHDOG_BARK_TIME=.*$", "CONFIG_QCOM_WATCHDOG_BARK_TIME=20000", c, flags=re.M)
    c=re.sub(r"^CONFIG_QCOM_WATCHDOG_PET_TIME=.*$", "CONFIG_QCOM_WATCHDOG_PET_TIME=15000", c, flags=re.M)
    cfg.write_text(c)

    (ROOT/"candidate-0046-watchdog-stock.txt").write_text(
        "healthy_stock_boot_sha256=e6f8c978c2cf0a9473d0ac73cdcf3ffb14747246fdc47f82245c43221eb4cbf1\n"
        "healthy_stock_ikconfig_bark_ms=20000\n"
        "healthy_stock_ikconfig_pet_ms=15000\n"
        "candidate_0036_bark_ms=11000\n"
        "candidate_0036_pet_ms=9360\n"
        "observed_failed_boot_reset_window_seconds=11.9-12.2\n"
        "qcom_wdt_bark_handler_action=qcom_wdt_trigger_bite\n"
        "mutation=relax donor Kconfig hard lock and restore exact healthy stock watchdog timing\n"
        "watchdog_disable=0\n"
        "CANDIDATE_0046_STOCK_WATCHDOG_GATE=PASS\n"
    )



def patch_tz_hyp_diagnostics():
    p=KERNEL/"drivers/firmware/qcom/tz_log.c"
    x=p.read_text()

    inc="#include <linux/qtee_shmbridge.h>\n"
    if x.count(inc) != 1:
        raise SystemExit(f"tz_log include anchor count={x.count(inc)}")
    x=x.replace(
        inc,
        inc+
        "#include <linux/workqueue.h>\n"
        "#include <linux/jiffies.h>\n",
        1,
    )

    anchor=(
        "static struct encrypted_log_info enc_qseelog_info;\n"
        "static struct encrypted_log_info enc_tzlog_info;\n"
        "\n"
        "/*\n"
        " * Debugfs data structure and functions\n"
        " */\n"
    )
    diag=(
        "static struct delayed_work lisa0040_secure_diag_work;\n"
        "static u32 lisa0040_last_hyp_off = ~0U;\n"
        "static u32 lisa0040_last_tz_off = ~0U;\n"
        "\n"
        "static void lisa0040_secure_diag_workfn(struct work_struct *work)\n"
        "{\n"
        "\tu32 hyp_magic = 0, hyp_cpu = 0, hyp_s2 = 0;\n"
        "\tu32 hyp_wrap = 0, hyp_off = 0, hyp_ring_off = 0;\n"
        "\tu32 tz_cpu = 0, tz_wrap = 0, tz_off = 0;\n"
        "\tu32 reset_type[TZBSP_MAX_CPU_COUNT] = { 0 };\n"
        "\tu32 reset_cnt[TZBSP_MAX_CPU_COUNT] = { 0 };\n"
        "\tbool hyp_ok = false, tz_ok = false;\n"
        "\tint i;\n"
        "\n"
        "\tif (tzdbg.is_hyplog_enabled && tzdbg.hyp_virt_iobase &&\n"
        "\t    tzdbg.hyp_diag_buf &&\n"
        "\t    tzdbg.hyp_debug_rw_buf_size >= sizeof(struct hypdbg_t)) {\n"
        "\t\tstruct hypdbg_t *hyp;\n"
        "\n"
        "\t\tmemcpy_fromio((void *)tzdbg.hyp_diag_buf,\n"
        "\t\t\ttzdbg.hyp_virt_iobase, tzdbg.hyp_debug_rw_buf_size);\n"
        "\t\thyp = tzdbg.hyp_diag_buf;\n"
        "\t\thyp_magic = hyp->magic_num;\n"
        "\t\thyp_cpu = hyp->cpu_count;\n"
        "\t\thyp_s2 = hyp->s2_fault_counter;\n"
        "\t\thyp_wrap = hyp->log_pos.wrap;\n"
        "\t\thyp_off = hyp->log_pos.offset;\n"
        "\t\thyp_ring_off = hyp->ring_off;\n"
        "\t\thyp_ok = true;\n"
        "\n"
        "\t\tif (hyp_ring_off < tzdbg.hyp_debug_rw_buf_size) {\n"
        "\t\t\tu32 log_len = tzdbg.hyp_debug_rw_buf_size - hyp_ring_off;\n"
        "\t\t\tif (log_len && hyp_off < log_len &&\n"
        "\t\t\t    hyp_off != lisa0040_last_hyp_off) {\n"
        "\t\t\t\tchar tail[65];\n"
        "\t\t\t\tu32 n = min_t(u32, 64, log_len);\n"
        "\t\t\t\tu8 *log = (u8 *)hyp + hyp_ring_off;\n"
        "\t\t\t\tfor (i = 0; i < n; i++) {\n"
        "\t\t\t\t\tu32 pos = (hyp_off + log_len - n + i) % log_len;\n"
        "\t\t\t\t\tu8 c = log[pos];\n"
        "\t\t\t\t\ttail[i] = (c >= 0x20 && c <= 0x7e) ? c : '.';\n"
        "\t\t\t\t}\n"
        "\t\t\t\ttail[n] = '\\0';\n"
        "\t\t\t\tpr_emerg(\"LISA0046: hyp_tail wrap=%u off=%u text=%s\\n\",\n"
        "\t\t\t\t\thyp_wrap, hyp_off, tail);\n"
        "\t\t\t\tlisa0040_last_hyp_off = hyp_off;\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t}\n"
        "\n"
        "\tif (!tzdbg.is_encrypted_log_enabled && tzdbg.virt_iobase &&\n"
        "\t    tzdbg.diag_buf && debug_rw_buf_size >= sizeof(struct tzdbg_t)) {\n"
        "\t\tstruct tzdbg_t *diag;\n"
        "\t\tu64 reset_end;\n"
        "\n"
        "\t\tmemcpy_fromio((void *)tzdbg.diag_buf,\n"
        "\t\t\ttzdbg.virt_iobase, debug_rw_buf_size);\n"
        "\t\tdiag = tzdbg.diag_buf;\n"
        "\t\ttz_cpu = min_t(u32, diag->cpu_count, TZBSP_MAX_CPU_COUNT);\n"
        "\t\treset_end = (u64)diag->reset_info_off +\n"
        "\t\t\t(u64)tz_cpu * sizeof(struct tzdbg_reset_info_t);\n"
        "\t\tif (diag->reset_info_off < debug_rw_buf_size &&\n"
        "\t\t    reset_end <= debug_rw_buf_size) {\n"
        "\t\t\tstruct tzdbg_reset_info_t *ri =\n"
        "\t\t\t\t(struct tzdbg_reset_info_t *)((u8 *)diag +\n"
        "\t\t\t\t diag->reset_info_off);\n"
        "\t\t\tfor (i = 0; i < tz_cpu; i++) {\n"
        "\t\t\t\treset_type[i] = ri[i].reset_type;\n"
        "\t\t\t\treset_cnt[i] = ri[i].reset_cnt;\n"
        "\t\t\t}\n"
        "\t\t\ttz_ok = true;\n"
        "\t\t}\n"
        "\n"
        "\t\tif (diag->ring_off < debug_rw_buf_size) {\n"
        "\t\t\tstruct tzdbg_log_t *log =\n"
        "\t\t\t\t(struct tzdbg_log_t *)((u8 *)diag + diag->ring_off);\n"
        "\t\t\tu32 log_len = diag->ring_len;\n"
        "\t\t\ttz_wrap = log->log_pos.wrap;\n"
        "\t\t\ttz_off = log->log_pos.offset;\n"
        "\t\t\tif (log_len &&\n"
        "\t\t\t    (u64)diag->ring_off + sizeof(struct tzdbg_log_pos_t) +\n"
        "\t\t\t    log_len <= debug_rw_buf_size && tz_off < log_len &&\n"
        "\t\t\t    tz_off != lisa0040_last_tz_off) {\n"
        "\t\t\t\tchar tail[65];\n"
        "\t\t\t\tu32 n = min_t(u32, 64, log_len);\n"
        "\t\t\t\tfor (i = 0; i < n; i++) {\n"
        "\t\t\t\t\tu32 pos = (tz_off + log_len - n + i) % log_len;\n"
        "\t\t\t\t\tu8 c = log->log_buf[pos];\n"
        "\t\t\t\t\ttail[i] = (c >= 0x20 && c <= 0x7e) ? c : '.';\n"
        "\t\t\t\t}\n"
        "\t\t\t\ttail[n] = '\\0';\n"
        "\t\t\t\tpr_emerg(\"LISA0046: tz_tail wrap=%u off=%u text=%s\\n\",\n"
        "\t\t\t\t\ttz_wrap, tz_off, tail);\n"
        "\t\t\t\tlisa0040_last_tz_off = tz_off;\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t}\n"
        "\n"
        "\tpr_emerg(\"LISA0046: secure_state hyplog=%d hyp_ok=%d enc=%d hyp_magic=0x%x hyp_cpu=%u s2=%u hyp_wrap=%u hyp_off=%u tz_ok=%d tz_cpu=%u r0=%x:%x r1=%x:%x r2=%x:%x r3=%x:%x\\n\",\n"
        "\t\ttzdbg.is_hyplog_enabled, hyp_ok,\n"
        "\t\ttzdbg.is_encrypted_log_enabled, hyp_magic, hyp_cpu, hyp_s2,\n"
        "\t\thyp_wrap, hyp_off, tz_ok, tz_cpu,\n"
        "\t\treset_type[0], reset_cnt[0], reset_type[1], reset_cnt[1],\n"
        "\t\treset_type[2], reset_cnt[2], reset_type[3], reset_cnt[3]);\n"
        "\n"
        "\tschedule_delayed_work(&lisa0040_secure_diag_work,\n"
        "\t\tmsecs_to_jiffies(500));\n"
        "}\n"
        "\n"
        "/*\n"
        " * Debugfs data structure and functions\n"
        " */\n"
    )
    if x.count(anchor) != 1:
        raise SystemExit(f"tz_log global diagnostic anchor count={x.count(anchor)}")
    x=x.replace(
        anchor,
        "static struct encrypted_log_info enc_qseelog_info;\n"
        "static struct encrypted_log_info enc_tzlog_info;\n"
        "\n"+diag,
        1,
    )

    old=(
        "\tif (tzdbgfs_init(pdev))\n"
        "\t\tgoto exit_free_disp_buf;\n"
        "\treturn 0;\n"
    )
    new=(
        "\tif (tzdbgfs_init(pdev))\n"
        "\t\tgoto exit_free_disp_buf;\n"
        "\tINIT_DELAYED_WORK(&lisa0040_secure_diag_work,\n"
        "\t\tlisa0040_secure_diag_workfn);\n"
        "\tschedule_delayed_work(&lisa0040_secure_diag_work,\n"
        "\t\tmsecs_to_jiffies(8000));\n"
        "\tpr_emerg(\"LISA0046: secure TZ/HYP diagnostic armed at +8000ms hyplog=%d enc=%d\\n\",\n"
        "\t\ttzdbg.is_hyplog_enabled, tzdbg.is_encrypted_log_enabled);\n"
        "\treturn 0;\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"tz_log probe diagnostic anchor count={x.count(old)}")
    x=x.replace(old,new,1)

    old=(
        "static int tz_log_remove(struct platform_device *pdev)\n"
        "{\n"
        "\ttzdbgfs_exit(pdev);\n"
    )
    new=(
        "static int tz_log_remove(struct platform_device *pdev)\n"
        "{\n"
        "\tcancel_delayed_work_sync(&lisa0040_secure_diag_work);\n"
        "\ttzdbgfs_exit(pdev);\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"tz_log remove diagnostic anchor count={x.count(old)}")
    x=x.replace(old,new,1)

    p.write_text(x)

    final=p.read_text()
    gates=[
        "LISA0046: secure TZ/HYP diagnostic armed at +8000ms",
        "LISA0046: secure_state hyplog=%d hyp_ok=%d enc=%d",
        "LISA0046: hyp_tail wrap=%u off=%u text=%s",
        "LISA0046: tz_tail wrap=%u off=%u text=%s",
        "msecs_to_jiffies(8000)",
        "msecs_to_jiffies(500)",
    ]
    for g in gates:
        if g not in final:
            raise SystemExit(f"TZ/HYP diagnostic gate missing: {g}")

    (ROOT/"candidate-0046-tz-hyp.txt").write_text(
        "purpose=read QTI TZ/HYP diagnostic buffers from Candidate kernel and persist them through existing FAST_TAIL without DEBUG_FS\\n"
        "source=drivers/firmware/qcom/tz_log.c\\n"
        "CONFIG_QTI_TZ_LOG_required=y\\n"
        "CONFIG_DEBUG_FS_required=0\\n"
        "poll_start_ms=8000\\n"
        "poll_interval_ms=500\\n"
        "watchdog_behavior_change=0\\n"
        "CANDIDATE_0046_TZ_HYP_DIAG_GATE=PASS\\n"
    )


def patch_restart_path_diagnostics():
    # Layer 1: persist the earliest Linux reboot/poweroff entry before
    # device_shutdown/syscore_shutdown can hide the caller.
    p=KERNEL/"kernel/reboot.c"
    x=p.read_text()

    old=(
        "void emergency_restart(void)\n"
        "{\n"
        "\tkmsg_dump(KMSG_DUMP_EMERG);\n"
    )
    new=(
        "void emergency_restart(void)\n"
        "{\n"
        "\tpr_emerg(\"LISA0046: emergency_restart entry\\n\");\n"
        "\tdump_stack();\n"
        "\tkmsg_dump(KMSG_DUMP_EMERG);\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"emergency_restart diagnostic anchor count={x.count(old)}")
    x=x.replace(old,new,1)

    old=(
        "void kernel_restart(char *cmd)\n"
        "{\n"
        "\tkernel_restart_prepare(cmd);\n"
    )
    new=(
        "void kernel_restart(char *cmd)\n"
        "{\n"
        "\tpr_emerg(\"LISA0046: kernel_restart entry cmd=%s\\n\", cmd ? cmd : \"<null>\");\n"
        "\tdump_stack();\n"
        "\t/* Diagnostic early dump: records caller before device shutdown. */\n"
        "\tkmsg_dump(KMSG_DUMP_RESTART);\n"
        "\tkernel_restart_prepare(cmd);\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"kernel_restart diagnostic anchor count={x.count(old)}")
    x=x.replace(old,new,1)

    old=(
        "void kernel_power_off(void)\n"
        "{\n"
        "\tkernel_shutdown_prepare(SYSTEM_POWER_OFF);\n"
    )
    new=(
        "void kernel_power_off(void)\n"
        "{\n"
        "\tpr_emerg(\"LISA0046: kernel_power_off entry\\n\");\n"
        "\tdump_stack();\n"
        "\t/* Diagnostic early dump: records caller before device shutdown. */\n"
        "\tkmsg_dump(KMSG_DUMP_POWEROFF);\n"
        "\tkernel_shutdown_prepare(SYSTEM_POWER_OFF);\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"kernel_power_off diagnostic anchor count={x.count(old)}")
    x=x.replace(old,new,1)
    p.write_text(x)

    # Layer 2: persist a second marker immediately before the Qualcomm
    # restart/poweroff handler reaches PS_HOLD.
    p=KERNEL/"drivers/power/reset/msm-poweroff.c"
    x=p.read_text()

    inc="#include <linux/reboot.h>\n"
    if x.count(inc) != 1:
        raise SystemExit(f"msm-poweroff reboot include anchor count={x.count(inc)}")
    x=x.replace(inc,inc+"#include <linux/kmsg_dump.h>\n",1)

    old=(
        "static void deassert_ps_hold(void)\n"
        "{\n"
        "\tqcom_scm_deassert_ps_hold();\n"
    )
    new=(
        "static void deassert_ps_hold(void)\n"
        "{\n"
        "\tpr_emerg(\"LISA0046: deassert_ps_hold reached\\n\");\n"
        "\tqcom_scm_deassert_ps_hold();\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"deassert_ps_hold diagnostic anchor count={x.count(old)}")
    x=x.replace(old,new,1)

    old=(
        "static int do_msm_restart(struct notifier_block *unused, unsigned long action,\n"
        "\t\t\t   void *arg)\n"
        "{\n"
        "\tconst char *cmd = arg;\n"
        "\n"
        "\tpr_notice(\"Going down for restart now\\n\");\n"
    )
    new=(
        "static int do_msm_restart(struct notifier_block *unused, unsigned long action,\n"
        "\t\t\t   void *arg)\n"
        "{\n"
        "\tconst char *cmd = arg;\n"
        "\n"
        "\tpr_emerg(\"LISA0046: do_msm_restart action=%lu cmd=%s\\n\",\n"
        "\t\t action, cmd ? cmd : \"<null>\");\n"
        "\tdump_stack();\n"
        "\t/* Persist the final Linux-side restart handler evidence before PS_HOLD. */\n"
        "\tkmsg_dump(KMSG_DUMP_RESTART);\n"
        "\tpr_notice(\"Going down for restart now\\n\");\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"do_msm_restart diagnostic anchor count={x.count(old)}")
    x=x.replace(old,new,1)

    old=(
        "static void do_msm_poweroff(void)\n"
        "{\n"
        "\tpr_notice(\"Powering off the SoC\\n\");\n"
    )
    new=(
        "static void do_msm_poweroff(void)\n"
        "{\n"
        "\tpr_emerg(\"LISA0046: do_msm_poweroff entry\\n\");\n"
        "\tdump_stack();\n"
        "\t/* Persist the final Linux-side poweroff evidence before PS_HOLD. */\n"
        "\tkmsg_dump(KMSG_DUMP_POWEROFF);\n"
        "\tpr_notice(\"Powering off the SoC\\n\");\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"do_msm_poweroff diagnostic anchor count={x.count(old)}")
    x=x.replace(old,new,1)
    p.write_text(x)

    reboot=(KERNEL/"kernel/reboot.c").read_text()
    power=(KERNEL/"drivers/power/reset/msm-poweroff.c").read_text()
    gates=[
        "LISA0046: emergency_restart entry",
        "LISA0046: kernel_restart entry cmd=%s",
        "LISA0046: kernel_power_off entry",
    ]
    for g in gates:
        if g not in reboot:
            raise SystemExit(f"restart diagnostic gate missing: {g}")
    gates=[
        "#include <linux/kmsg_dump.h>",
        "LISA0046: do_msm_restart action=%lu cmd=%s",
        "LISA0046: do_msm_poweroff entry",
        "LISA0046: deassert_ps_hold reached",
        "kmsg_dump(KMSG_DUMP_RESTART);",
        "kmsg_dump(KMSG_DUMP_POWEROFF);",
    ]
    for g in gates:
        if g not in power:
            raise SystemExit(f"PS_HOLD diagnostic gate missing: {g}")

    (ROOT/"candidate-0046-restart-diagnostics.txt").write_text(
        "evidence=deep-log shows PSHOLD hard reset without panic/oops/watchdog and no stable gain below 4KiB tail\n"
        "control=drivers/power/reset/msm-poweroff.c and qcom-pon.c match known-good source blobs\n"
        "strategy=prove_or_exclude_normal_linux_restart_poweroff_path\n"
        "kernel_restart_entry=marker+dump_stack+early_kmsg_dump\n"
        "kernel_poweroff_entry=marker+dump_stack+early_kmsg_dump\n"
        "emergency_restart_entry=marker+dump_stack+existing_kmsg_dump\n"
        "msm_restart_handler=marker+dump_stack+kmsg_dump_before_pshold\n"
        "msm_poweroff_handler=marker+dump_stack+kmsg_dump_before_pshold\n"
        "deassert_ps_hold=marker\n"
        "fast_tail_bytes=4096\n"
        "snapshot_interval_milliseconds=10\n"
        "CANDIDATE_0046_RESTART_PATH_DIAG_GATE=PASS\n"
    )



def patch_ipa_pil_stage_trace():
    p=KERNEL/"drivers/soc/qcom/peripheral-loader.c"
    x=p.read_text()

    old=(
        "\tif (desc->subsys_vmid > 0) {\n"
        "\t\ttrace_pil_event(\"before_reclaim_mem\", desc);\n"
    )
    new=(
        "\tif (!strcmp(desc->name, \"yupik_ipa_fws\"))\n"
        "\t\tpr_emerg(\"LISA0046_IPA_PIL stage=segments_loaded name=%s\\n\", desc->name);\n"
        "\n"
        "\tif (desc->subsys_vmid > 0) {\n"
        "\t\ttrace_pil_event(\"before_reclaim_mem\", desc);\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"IPA PIL segments anchor count={x.count(old)}")
    x=x.replace(old,new,1)

    old=(
        "\ttrace_pil_event(\"before_auth_reset\", desc);\n"
        "\tnotify_before_auth_and_reset(desc->dev);\n"
        "\tret = desc->ops->auth_and_reset(desc);\n"
    )
    new=(
        "\ttrace_pil_event(\"before_auth_reset\", desc);\n"
        "\tif (!strcmp(desc->name, \"yupik_ipa_fws\"))\n"
        "\t\tpr_emerg(\"LISA0046_IPA_PIL stage=before_notify name=%s\\n\", desc->name);\n"
        "\tnotify_before_auth_and_reset(desc->dev);\n"
        "\tif (!strcmp(desc->name, \"yupik_ipa_fws\"))\n"
        "\t\tpr_emerg(\"LISA0046_IPA_PIL stage=after_notify name=%s\\n\", desc->name);\n"
        "\tif (!strcmp(desc->name, \"yupik_ipa_fws\"))\n"
        "\t\tpr_emerg(\"LISA0046_IPA_PIL stage=before_auth_reset name=%s\\n\", desc->name);\n"
        "\tret = desc->ops->auth_and_reset(desc);\n"
        "\tif (!strcmp(desc->name, \"yupik_ipa_fws\"))\n"
        "\t\tpr_emerg(\"LISA0046_IPA_PIL stage=after_auth_reset ret=%d name=%s\\n\", ret, desc->name);\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"IPA PIL auth anchor count={x.count(old)}")
    x=x.replace(old,new,1)
    p.write_text(x)

    p=KERNEL/"drivers/soc/qcom/subsys-pil-tz.c"
    x=p.read_text()

    old=(
        "\tif (d->subsys_desc.no_auth)\n"
        "\t\treturn 0;\n"
        "\n"
        "\trc = scm_pas_enable_bw();\n"
    )
    new=(
        "\tif (d->subsys_desc.no_auth)\n"
        "\t\treturn 0;\n"
        "\n"
        "\tif (!strcmp(pil->name, \"yupik_ipa_fws\"))\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=entry pas_id=%u\\n\", d->pas_id);\n"
        "\n"
        "\trc = scm_pas_enable_bw();\n"
        "\tif (!strcmp(pil->name, \"yupik_ipa_fws\"))\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=after_bw rc=%d\\n\", rc);\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"IPA SCM entry anchor count={x.count(old)}")
    x=x.replace(old,new,1)

    old=(
        "\trc = enable_regulators(d, pil->dev, d->regs, d->reg_count, false);\n"
        "\tif (rc)\n"
        "\t\treturn rc;\n"
        "\n"
        "\trc = prepare_enable_clocks(pil->dev, d->clks, d->clk_count);\n"
        "\tif (rc)\n"
        "\t\tgoto err_clks;\n"
        "\n"
        "\tscm_ret = qcom_scm_pas_auth_and_reset(d->pas_id);\n"
    )
    new=(
        "\trc = enable_regulators(d, pil->dev, d->regs, d->reg_count, false);\n"
        "\tif (!strcmp(pil->name, \"yupik_ipa_fws\"))\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=after_regulators rc=%d count=%d\\n\", rc, d->reg_count);\n"
        "\tif (rc)\n"
        "\t\treturn rc;\n"
        "\n"
        "\trc = prepare_enable_clocks(pil->dev, d->clks, d->clk_count);\n"
        "\tif (!strcmp(pil->name, \"yupik_ipa_fws\"))\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=after_clocks rc=%d count=%d\\n\", rc, d->clk_count);\n"
        "\tif (rc)\n"
        "\t\tgoto err_clks;\n"
        "\n"
        "\tif (!strcmp(pil->name, \"yupik_ipa_fws\"))\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=before_pas_auth_reset pas_id=%u\\n\", d->pas_id);\n"
        "\tscm_ret = qcom_scm_pas_auth_and_reset(d->pas_id);\n"
        "\tif (!strcmp(pil->name, \"yupik_ipa_fws\"))\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=after_pas_auth_reset ret=%u\\n\", scm_ret);\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"IPA SCM PAS anchor count={x.count(old)}")
    x=x.replace(old,new,1)
    p.write_text(x)

    outer=(KERNEL/"drivers/soc/qcom/peripheral-loader.c").read_text()
    inner=(KERNEL/"drivers/soc/qcom/subsys-pil-tz.c").read_text()
    outer_gates=[
        "LISA0046_IPA_PIL stage=segments_loaded",
        "LISA0046_IPA_PIL stage=before_notify",
        "LISA0046_IPA_PIL stage=after_notify",
        "LISA0046_IPA_PIL stage=before_auth_reset",
        "LISA0046_IPA_PIL stage=after_auth_reset",
    ]
    inner_gates=[
        "LISA0046_IPA_SCM stage=entry",
        "LISA0046_IPA_SCM stage=after_bw",
        "LISA0046_IPA_SCM stage=after_regulators",
        "LISA0046_IPA_SCM stage=after_clocks",
        "LISA0046_IPA_SCM stage=before_pas_auth_reset",
        "LISA0046_IPA_SCM stage=after_pas_auth_reset",
    ]
    for g in outer_gates:
        if g not in outer:
            raise SystemExit(f"IPA PIL trace gate missing: {g}")
    for g in inner_gates:
        if g not in inner:
            raise SystemExit(f"IPA SCM trace gate missing: {g}")

    (ROOT/"candidate-0046-ipa-pil-trace.txt").write_text(
        "evidence=Candidate0040 and Candidate0041 both stop immediately after yupik_ipa_fws loading\\n"
        "healthy_oracle=known-good boot continues to Brought out of reset, IPA FW loaded successfully, IPA driver initialization was successful\\n"
        "peripheral_loader_source=donor and known-good blob-identical\\n"
        "subsys_pil_tz_source=donor and known-good blob-identical\\n"
        "yupik_dtsi=donor and known-good blob-identical\\n"
        "strategy=trace exact IPA PIL/SCM stage without changing behavior\\n"
        "CANDIDATE_0046_IPA_PIL_TRACE_GATE=PASS\\n"
    )



def patch_ipa_pas_sync_checkpoint():
    p=KERNEL/"drivers/mtd/mtdoops.c"
    x=p.read_text()

    old="\tunsigned int snapshot_seq;\n"
    new=(
        "\tunsigned int snapshot_seq;\n"
        "\tstruct mutex snapshot_lock;\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"sync checkpoint context anchor count={x.count(old)}")
    x=x.replace(old,new,1)

    include_anchor="#include <linux/module.h>\n"
    if include_anchor not in x:
        raise SystemExit("mtdoops module include anchor missing")
    if "#include <linux/mutex.h>\n" not in x:
        x=x.replace(include_anchor, include_anchor+"#include <linux/mutex.h>\n", 1)

    old=(
        "\tif (!cxt->mtd)\n"
        "\t\treturn;\n"
        "\n"
        "\t/* Fast-tail snapshots overwrite block2mtd directly; no 2MiB erase. */\n"
    )
    new=(
        "\tif (!cxt->mtd)\n"
        "\t\treturn;\n"
        "\n"
        "\tmutex_lock(&cxt->snapshot_lock);\n"
        "\t/* Fast-tail snapshots overwrite block2mtd directly; no 2MiB erase. */\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"sync checkpoint snapshot lock anchor count={x.count(old)}")
    x=x.replace(old,new,1)

    old=(
        "\tif (got && len) {\n"
        "\t\tmtdoops_snapshot_write_fast(cxt, len);\n"
        "\t\tcxt->snapshot_seq++;\n"
        "\t\tprintk(KERN_INFO \"mtdoops: Lisa Candidate 0046 snapshot %u persisted (%zu bytes)\\n\",\n"
        "\t\t       cxt->snapshot_seq, len);\n"
        "\t}\n"
        "\n"
        "\tif (cxt->mtd)\n"
    )
    new=(
        "\tif (got && len) {\n"
        "\t\tmtdoops_snapshot_write_fast(cxt, len);\n"
        "\t\tcxt->snapshot_seq++;\n"
        "\t\tprintk(KERN_INFO \"mtdoops: Lisa Candidate 0046 snapshot %u persisted (%zu bytes)\\n\",\n"
        "\t\t       cxt->snapshot_seq, len);\n"
        "\t}\n"
        "\tmutex_unlock(&cxt->snapshot_lock);\n"
        "\n"
        "\tif (cxt->mtd)\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"sync checkpoint snapshot unlock anchor count={x.count(old)}")
    x=x.replace(old,new,1)

    anchor="static void mtdoops_snapshot_workfunc(struct work_struct *work)\n"
    if x.count(anchor) != 1:
        raise SystemExit(f"sync helper insertion anchor count={x.count(anchor)}")

    helper=(
        "void lisa_mtdoops_checkpoint(const char *tag)\n"
        "{\n"
        "\tstruct mtdoops_context *cxt = &oops_cxt;\n"
        "\tsize_t len = 0;\n"
        "\tbool got;\n"
        "\n"
        "\tif (!cxt->mtd || !cxt->oops_buf)\n"
        "\t\treturn;\n"
        "\n"
        "\tmutex_lock(&cxt->snapshot_lock);\n"
        "\tpr_emerg(\"LISA0046_SYNC_CHECKPOINT tag=%s\\n\", tag);\n"
        "\tcxt->snapshot_dump.active = true;\n"
        "\tkmsg_dump_rewind(&cxt->snapshot_dump);\n"
        "\tgot = kmsg_dump_get_buffer(&cxt->snapshot_dump, true,\n"
        "\t\t\tcxt->oops_buf + MTDOOPS_HEADER_SIZE + 8,\n"
        "\t\t\tMTDOOPS_FAST_TAIL_BYTES, &len);\n"
        "\tcxt->snapshot_dump.active = false;\n"
        "\tif (got && len)\n"
        "\t\tmtdoops_snapshot_write_fast(cxt, len);\n"
        "\tmutex_unlock(&cxt->snapshot_lock);\n"
        "}\n"
        "EXPORT_SYMBOL_GPL(lisa_mtdoops_checkpoint);\n"
        "\n"
    )
    x=x.replace(anchor,helper+anchor,1)

    old=(
        "\tINIT_DELAYED_WORK(&cxt->work_snapshot, mtdoops_snapshot_workfunc);\n"
        "\tcxt->snapshot_seq = 0;\n"
    )
    new=(
        "\tINIT_DELAYED_WORK(&cxt->work_snapshot, mtdoops_snapshot_workfunc);\n"
        "\tmutex_init(&cxt->snapshot_lock);\n"
        "\tcxt->snapshot_seq = 0;\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"sync checkpoint init anchor count={x.count(old)}")
    x=x.replace(old,new,1)
    p.write_text(x)

    p=KERNEL/"drivers/soc/qcom/subsys-pil-tz.c"
    x=p.read_text()
    include_anchor="#include <linux/module.h>\n"
    if include_anchor not in x:
        raise SystemExit("subsys-pil-tz module include anchor missing")
    x=x.replace(
        include_anchor,
        include_anchor+"extern void lisa_mtdoops_checkpoint(const char *tag);\n",
        1
    )

    old=(
        "\tif (!strcmp(pil->name, \"yupik_ipa_fws\"))\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=before_pas_auth_reset pas_id=%u\\n\", d->pas_id);\n"
        "\tscm_ret = qcom_scm_pas_auth_and_reset(d->pas_id);\n"
        "\tif (!strcmp(pil->name, \"yupik_ipa_fws\"))\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=after_pas_auth_reset ret=%u\\n\", scm_ret);\n"
    )
    new=(
        "\tif (!strcmp(pil->name, \"yupik_ipa_fws\")) {\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=before_pas_auth_reset pas_id=%u\\n\", d->pas_id);\n"
        "\t\tlisa_mtdoops_checkpoint(\"ipa_before_pas_auth_reset\");\n"
        "\t}\n"
        "\tscm_ret = qcom_scm_pas_auth_and_reset(d->pas_id);\n"
        "\tif (!strcmp(pil->name, \"yupik_ipa_fws\")) {\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=after_pas_auth_reset ret=%u\\n\", scm_ret);\n"
        "\t\tlisa_mtdoops_checkpoint(\"ipa_after_pas_auth_reset\");\n"
        "\t}\n"
    )
    if x.count(old) != 1:
        raise SystemExit(f"sync PAS call anchor count={x.count(old)}")
    x=x.replace(old,new,1)
    p.write_text(x)

    m=(KERNEL/"drivers/mtd/mtdoops.c").read_text()
    q=(KERNEL/"drivers/soc/qcom/subsys-pil-tz.c").read_text()
    gates=[
        "void lisa_mtdoops_checkpoint(const char *tag)",
        "LISA0046_SYNC_CHECKPOINT tag=%s",
        "EXPORT_SYMBOL_GPL(lisa_mtdoops_checkpoint);",
        "#include <linux/mutex.h>",
        "struct mutex snapshot_lock;",
        "mutex_init(&cxt->snapshot_lock);",
    ]
    for g in gates:
        if g not in m:
            raise SystemExit(f"sync mtdoops gate missing: {g}")
    gates=[
        'lisa_mtdoops_checkpoint("ipa_before_pas_auth_reset");',
        'lisa_mtdoops_checkpoint("ipa_after_pas_auth_reset");',
    ]
    for g in gates:
        if g not in q:
            raise SystemExit(f"sync PAS gate missing: {g}")

    (ROOT/"candidate-0046-ipa-pas-sync-checkpoint.txt").write_text(
        "evidence=Candidate0042 periodic trace persisted through after_regulators rc=0 count=0 only\\n"
        "dt_fact=qcom,ipa_fws has no active-clock-names and no active-reg-names\\n"
        "source_fact=prepare_enable_clocks returns 0 immediately when clk_count=0\\n"
        "ambiguity=10ms periodic snapshot can miss markers immediately before secure reset\\n"
        "strategy=synchronously persist one fast-tail checkpoint immediately before and after PAS auth/reset\\n"
        "behavior=qcom_scm_pas_auth_and_reset call itself unchanged\\n"
        "CANDIDATE_0046_IPA_PAS_SYNC_GATE=PASS\\n"
    )



def patch_ipa_pas_shmbridge():
    p=KERNEL/"drivers/soc/qcom/subsys-pil-tz.c"
    x=p.read_text()

    include_anchor="#include <linux/qcom_scm.h>\n"
    include_new=include_anchor+"#include <linux/qtee_shmbridge.h>\n"
    if x.count(include_anchor) != 1:
        raise SystemExit(f"SHMBridge include anchor count={x.count(include_anchor)}")
    if "#include <linux/qtee_shmbridge.h>\n" not in x:
        x=x.replace(include_anchor,include_new,1)

    struct_old=(
        "\tu32 pas_id;\n"
        "\tstruct icc_path *bus_client;\n"
    )
    struct_new=(
        "\tu32 pas_id;\n"
        "\tphys_addr_t lisa_ipa_fw_addr;\n"
        "\tsize_t lisa_ipa_fw_size;\n"
        "\tbool lisa_ipa_fw_region_valid;\n"
        "\tstruct icc_path *bus_client;\n"
    )
    if x.count(struct_old) != 1:
        raise SystemExit(f"IPA saved-region struct anchor count={x.count(struct_old)}")
    x=x.replace(struct_old,struct_new,1)

    mem_old=(
        "\tsize += pil->extra_size;\n"
        "\tscm_ret = qcom_scm_pas_mem_setup(d->pas_id, addr, size);\n"
    )
    mem_new=(
        "\tsize += pil->extra_size;\n"
        "\tif (!strcmp(pil->name, \"yupik_ipa_fws\") && d->pas_id == 0x0f) {\n"
        "\t\td->lisa_ipa_fw_addr = addr;\n"
        "\t\td->lisa_ipa_fw_size = size;\n"
        "\t\td->lisa_ipa_fw_region_valid = true;\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SHMBRIDGE stage=mem_setup_save addr=%pa size=%zu pas_id=%u\\n\",\n"
        "\t\t\t &d->lisa_ipa_fw_addr, d->lisa_ipa_fw_size, d->pas_id);\n"
        "\t}\n"
        "\tscm_ret = qcom_scm_pas_mem_setup(d->pas_id, addr, size);\n"
    )
    if x.count(mem_old) != 1:
        raise SystemExit(f"IPA mem_setup save anchor count={x.count(mem_old)}")
    x=x.replace(mem_old,mem_new,1)

    decl_old=(
        "\tstruct pil_tz_data *d = desc_to_data(pil);\n"
        "\tint rc;\n"
        "\tu32 scm_ret = 0;\n"
        "\tunsigned long pfn_start, pfn_end, pfn;\n"
        "\n"
        "\tif (d->subsys_desc.no_auth)\n"
        "\t\treturn 0;\n"
    )
    decl_new=(
        "\tstruct pil_tz_data *d = desc_to_data(pil);\n"
        "\tint rc;\n"
        "\tint shm_ret = 0;\n"
        "\tint shm_query = 0;\n"
        "\tu32 scm_ret = 0;\n"
        "\tunsigned long pfn_start, pfn_end, pfn;\n"
        "\tu32 ns_vmid_list[] = { VMID_HLOS };\n"
        "\tu32 ns_vm_perm_list[] = { PERM_READ | PERM_WRITE };\n"
        "\tu64 shm_handle = 0;\n"
        "\tbool shm_owned = false;\n"
        "\tbool ipa_target;\n"
        "\n"
        "\tif (d->subsys_desc.no_auth)\n"
        "\t\treturn 0;\n"
        "\n"
        "\tipa_target = !strcmp(pil->name, \"yupik_ipa_fws\") && d->pas_id == 0x0f;\n"
    )
    if x.count(decl_old) != 1:
        raise SystemExit(f"IPA auth declaration anchor count={x.count(decl_old)}")
    x=x.replace(decl_old,decl_new,1)

    pas_old=(
        "\tif (!strcmp(pil->name, \"yupik_ipa_fws\")) {\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=before_pas_auth_reset pas_id=%u\\n\", d->pas_id);\n"
        "\t\tlisa_mtdoops_checkpoint(\"ipa_before_pas_auth_reset\");\n"
        "\t}\n"
        "\tscm_ret = qcom_scm_pas_auth_and_reset(d->pas_id);\n"
        "\tif (!strcmp(pil->name, \"yupik_ipa_fws\")) {\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=after_pas_auth_reset ret=%u\\n\", scm_ret);\n"
        "\t\tlisa_mtdoops_checkpoint(\"ipa_after_pas_auth_reset\");\n"
        "\t}\n"
    )
    pas_new=(
        "\tif (ipa_target) {\n"
        "\t\tif (!d->lisa_ipa_fw_region_valid || !d->lisa_ipa_fw_size) {\n"
        "\t\t\tpr_emerg(\"LISA0046_IPA_SHMBRIDGE stage=invalid_saved_region valid=%d size=%zu\\n\",\n"
        "\t\t\t\t d->lisa_ipa_fw_region_valid, d->lisa_ipa_fw_size);\n"
        "\t\t\tlisa_mtdoops_checkpoint(\"ipa_before_shmbridge\");\n"
        "\t\t\tlisa_mtdoops_checkpoint(\"ipa_after_shmbridge\");\n"
        "\t\t\trc = -EINVAL;\n"
        "\t\t\tgoto err_lisa_pas;\n"
        "\t\t}\n"
        "\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SHMBRIDGE stage=before_register addr=%pa size=%zu enabled=%d\\n\",\n"
        "\t\t\t &d->lisa_ipa_fw_addr, d->lisa_ipa_fw_size,\n"
        "\t\t\t qtee_shmbridge_is_enabled());\n"
        "\t\tlisa_mtdoops_checkpoint(\"ipa_before_shmbridge\");\n"
        "\n"
        "\t\tif (!qtee_shmbridge_is_enabled()) {\n"
        "\t\t\tpr_emerg(\"LISA0046_IPA_SHMBRIDGE stage=register_skipped reason=disabled\\n\");\n"
        "\t\t\tlisa_mtdoops_checkpoint(\"ipa_after_shmbridge\");\n"
        "\t\t\trc = -EOPNOTSUPP;\n"
        "\t\t\tgoto err_lisa_pas;\n"
        "\t\t}\n"
        "\n"
        "\t\tshm_query = qtee_shmbridge_query(d->lisa_ipa_fw_addr);\n"
        "\t\tif (shm_query == -EEXIST) {\n"
        "\t\t\tpr_emerg(\"LISA0046_IPA_SHMBRIDGE stage=query existing=1 action=abort_before_pas addr=%pa size=%zu\\n\",\n"
        "\t\t\t\t &d->lisa_ipa_fw_addr, d->lisa_ipa_fw_size);\n"
        "\t\t\tlisa_mtdoops_checkpoint(\"ipa_after_shmbridge\");\n"
        "\t\t\trc = -EALREADY;\n"
        "\t\t\tgoto err_lisa_pas;\n"
        "\t\t} else if (shm_query) {\n"
        "\t\t\tpr_emerg(\"LISA0046_IPA_SHMBRIDGE stage=query_failed rc=%d addr=%pa\\n\",\n"
        "\t\t\t\t shm_query, &d->lisa_ipa_fw_addr);\n"
        "\t\t\tlisa_mtdoops_checkpoint(\"ipa_after_shmbridge\");\n"
        "\t\t\trc = shm_query;\n"
        "\t\t\tgoto err_lisa_pas;\n"
        "\t\t} else {\n"
        "\t\t\tshm_ret = qtee_shmbridge_register(d->lisa_ipa_fw_addr,\n"
        "\t\t\t\t\td->lisa_ipa_fw_size,\n"
        "\t\t\t\t\tns_vmid_list, ns_vm_perm_list, 1,\n"
        "\t\t\t\t\tPERM_READ | PERM_WRITE, &shm_handle);\n"
        "\t\t\tpr_emerg(\"LISA0046_IPA_SHMBRIDGE stage=after_register rc=%d handle=%llu addr=%pa size=%zu\\n\",\n"
        "\t\t\t\t shm_ret, shm_handle, &d->lisa_ipa_fw_addr,\n"
        "\t\t\t\t d->lisa_ipa_fw_size);\n"
        "\t\t\tlisa_mtdoops_checkpoint(\"ipa_after_shmbridge\");\n"
        "\t\t\tif (shm_ret) {\n"
        "\t\t\t\trc = shm_ret;\n"
        "\t\t\t\tgoto err_lisa_pas;\n"
        "\t\t\t}\n"
        "\t\t\tshm_owned = true;\n"
        "\t\t}\n"
        "\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=before_pas_auth_reset pas_id=%u bridge_owned=%d existing=%d\\n\",\n"
        "\t\t\t d->pas_id, shm_owned, shm_query == -EEXIST);\n"
        "\t\tlisa_mtdoops_checkpoint(\"ipa_before_pas_auth_reset\");\n"
        "\t}\n"
        "\tscm_ret = qcom_scm_pas_auth_and_reset(d->pas_id);\n"
        "\tif (ipa_target) {\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SCM stage=after_pas_auth_reset ret=%u\\n\", scm_ret);\n"
        "\t\tlisa_mtdoops_checkpoint(\"ipa_after_pas_auth_reset\");\n"
        "\t\tif (shm_owned) {\n"
        "\t\t\tshm_ret = qtee_shmbridge_deregister(shm_handle);\n"
        "\t\t\tpr_emerg(\"LISA0046_IPA_SHMBRIDGE stage=deregister rc=%d handle=%llu\\n\",\n"
        "\t\t\t\t shm_ret, shm_handle);\n"
        "\t\t\tshm_owned = false;\n"
        "\t\t}\n"
        "\t}\n"
    )
    if x.count(pas_old) != 1:
        raise SystemExit(f"IPA PAS SHMBridge call anchor count={x.count(pas_old)}")
    x=x.replace(pas_old,pas_new,1)

    cleanup_old=(
        "\tscm_pas_disable_bw();\n"
        "\tif (rc)\n"
        "\t\tgoto err_reset;\n"
        "\n"
        "\treturn scm_ret;\n"
        "err_reset:\n"
    )
    cleanup_new=(
        "\tscm_pas_disable_bw();\n"
        "\tif (rc)\n"
        "\t\tgoto err_reset;\n"
        "\n"
        "\treturn scm_ret;\n"
        "err_lisa_pas:\n"
        "\tif (shm_owned) {\n"
        "\t\tshm_ret = qtee_shmbridge_deregister(shm_handle);\n"
        "\t\tpr_emerg(\"LISA0046_IPA_SHMBRIDGE stage=error_deregister rc=%d handle=%llu\\n\",\n"
        "\t\t\t shm_ret, shm_handle);\n"
        "\t\tshm_owned = false;\n"
        "\t}\n"
        "\tscm_pas_disable_bw();\n"
        "err_reset:\n"
    )
    if x.count(cleanup_old) != 1:
        raise SystemExit(f"IPA PAS cleanup anchor count={x.count(cleanup_old)}")
    x=x.replace(cleanup_old,cleanup_new,1)

    p.write_text(x)
    out=p.read_text()
    gates=[
        "#include <linux/qtee_shmbridge.h>",
        "phys_addr_t lisa_ipa_fw_addr;",
        "size_t lisa_ipa_fw_size;",
        "qtee_shmbridge_is_enabled()",
        "qtee_shmbridge_query(d->lisa_ipa_fw_addr)",
        "qtee_shmbridge_register(d->lisa_ipa_fw_addr",
        "VMID_HLOS",
        "PERM_READ | PERM_WRITE",
        'lisa_mtdoops_checkpoint("ipa_before_shmbridge");',
        'lisa_mtdoops_checkpoint("ipa_after_shmbridge");',
        'lisa_mtdoops_checkpoint("ipa_before_pas_auth_reset");',
        'lisa_mtdoops_checkpoint("ipa_after_pas_auth_reset");',
        "qtee_shmbridge_deregister(shm_handle)",
        "err_lisa_pas:",
    ]
    for g in gates:
        if g not in out:
            raise SystemExit(f"IPA PAS SHMBridge gate missing: {g}")

    (ROOT/"candidate-0046-ipa-pas-shmbridge.txt").write_text(
        "baseline=Candidate0043 synchronous IPA PAS checkpoint path\n"
        "target_firmware=yupik_ipa_fws\n"
        "target_pas_id=0x0f\n"
        "region_source=exact addr+size passed to qcom_scm_pas_mem_setup after pil->extra_size\n"
        "bridge_ns_vmid=VMID_HLOS\n"
        "bridge_ns_perm=PERM_READ|PERM_WRITE\n"
        "bridge_tz_perm=PERM_READ|PERM_WRITE\n"
        "failure_policy=never call PAS when bridge mechanism/register/query preparation fails\n"
        "existing_policy=do not duplicate exact-paddr bridge; abort before PAS and inspect ownership/VMID state\n"
        "cleanup_policy=deregister only a bridge created by Candidate0045 when PAS returns or local error unwinds\n"
        "checkpoint_1=ipa_before_shmbridge\n"
        "checkpoint_2=ipa_after_shmbridge\n"
        "checkpoint_3=ipa_before_pas_auth_reset\n"
        "checkpoint_4=ipa_after_pas_auth_reset\n"
        "CANDIDATE_0046_IPA_PAS_SHMBRIDGE_GATE=PASS\n"
    )


def repack():
    PAGE=4096
    stock=bytearray(STOCK_BOOT.read_bytes())
    kernel=(ROOT/"candidate-0046-Image").read_bytes()
    if stock[:8] != b"ANDROID!":
        raise SystemExit("bad stock boot magic")
    ksz=struct.unpack_from("<I",stock,8)[0]
    rsz=struct.unpack_from("<I",stock,12)[0]
    if ksz != STOCK_KERNEL_SIZE or rsz != STOCK_RAMDISK_SIZE:
        raise SystemExit("stock boot layout mismatch")
    if len(kernel) > ksz:
        raise SystemExit("candidate Image exceeds stock kernel region")
    if struct.unpack_from("<I",kernel,0x38)[0] != 0x644D5241:
        raise SystemExit("ARM64 Image magic missing")
    roff=align(PAGE+ksz,PAGE)
    ramdisk=bytes(stock[roff:roff+rsz])
    if sha256(ramdisk) != STOCK_RAMDISK_SHA:
        raise SystemExit("stock ramdisk mismatch")
    original=bytes(stock)
    stock[PAGE:PAGE+ksz]=b"\0"*ksz
    stock[PAGE:PAGE+len(kernel)]=kernel
    out=bytes(stock)
    if out[:PAGE] != original[:PAGE]:
        raise SystemExit("header page changed")
    if out[PAGE+ksz:] != original[PAGE+ksz:]:
        raise SystemExit("non-kernel bytes changed")
    logical_end=align(roff+rsz,PAGE)
    if original[logical_end:logical_end+4] != b"AVB0":
        raise SystemExit("stock AVB0 missing")
    if original[-64:-60] != b"AVBf":
        raise SystemExit("stock AVBf missing")
    if out[logical_end:logical_end+4] != original[logical_end:logical_end+4]:
        raise SystemExit("AVB0 changed")
    if out[-64:] != original[-64:]:
        raise SystemExit("AVB footer changed")
    (ROOT/"boot.img").write_bytes(out)
    (ROOT/"boot.img.sha256").write_text(f"{sha256(out)}  boot.img\n")
    (ROOT/"candidate-0046-repack.txt").write_text(
        f"candidate_0046_image_sha256={sha256(kernel)}\n"
        f"candidate_0046_image_bytes={len(kernel)}\n"
        f"stock_kernel_region_bytes={ksz}\n"
        f"kernel_zero_pad_bytes={ksz-len(kernel)}\n"
        f"candidate_0046_boot_sha256={sha256(out)}\n"
        "boot_header_byte_exact=1\n"
        "stock_ramdisk_byte_exact=1\n"
        "changed_bytes_outside_kernel_region=0\n"
        "stock_avb0_metadata_byte_exact=1\n"
        "stock_avbf_footer_byte_exact=1\n"
        "CANDIDATE_0046_FIXED_REGION_REPACK_GATE=PASS\n"
    )

def main():
    if sha256(STOCK_BOOT) != STOCK_BOOT_SHA or STOCK_BOOT.stat().st_size != STOCK_BOOT_BYTES:
        raise SystemExit("healthy stock boot authentication failed")
    if subprocess.check_output(["git","-C",str(KERNEL),"rev-parse","HEAD"], text=True).strip() != SOURCE_SHA:
        raise SystemExit("kernel source SHA mismatch")
    for name in ["vendor_boot.img","dtbo.img","vbmeta.img","vbmeta_system.img"]:
        p=ROOT/"reconstruction/stock/stock-Image-3.09"/name
        if not p.is_file() or p.stat().st_size == 0:
            raise SystemExit(f"missing companion {name}")
        if p.read_bytes()[:96].startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise SystemExit(f"LFS pointer not materialized: {name}")
    cfg_path=ROOT/"candidate-0018.ikconfig"
    if not cfg_path.is_file() or cfg_path.stat().st_size == 0:
        raise SystemExit("preserved Candidate 0018 IKCONFIG missing")
    cfg=cfg_path.read_bytes()
    if b"CONFIG_INTERCONNECT_QCOM_RPMH=y" not in cfg:
        raise SystemExit("expected RPMH config missing")
    if b"CONFIG_MODVERSIONS=y" not in cfg:
        raise SystemExit("expected MODVERSIONS config missing")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/".config").write_bytes(cfg)

    overlay_known_good()
    patch_stock_rwsem()
    patch_block2mtd_devpath()
    patch_mtdoops_persistence()
    patch_mtdoops_periodic_snapshot()
    patch_mtdoops_fast_snapshot_io()
    patch_qgki_module_abi()
    patch_display_module_mode()
    patch_gpu_gpulist()
    patch_yupik()
    patch_stock_watchdog_timings()
    patch_tz_hyp_diagnostics()
    patch_restart_path_diagnostics()
    patch_ipa_pil_stage_trace()
    patch_ipa_pas_sync_checkpoint()
    patch_ipa_pas_shmbridge()

    env=os.environ.copy()
    sh(["make","-j"+str(os.cpu_count() or 4),"O=out","ARCH=arm64","CC=clang","LLVM=1","LLVM_IAS=1",
        "CROSS_COMPILE=aarch64-linux-gnu-","CROSS_COMPILE_COMPAT=arm-linux-gnueabi-",
        "CLANG_TRIPLE=aarch64-linux-gnu-","olddefconfig"], cwd=KERNEL, env=env)
    cfg_text=(OUT/".config").read_text()
    if "CONFIG_QCOM_WATCHDOG_BARK_TIME=20000\n" not in cfg_text:
        raise SystemExit("Candidate 0046 effective bark time is not stock 20000ms")
    if "CONFIG_QCOM_WATCHDOG_PET_TIME=15000\n" not in cfg_text:
        raise SystemExit("Candidate 0046 effective pet time is not stock 15000ms")
    if "CONFIG_QTI_TZ_LOG=y\n" not in cfg_text:
        raise SystemExit("Candidate 0046 QTI_TZ_LOG is not enabled")
    if "CONFIG_QCOM_KGSL=y\n" not in cfg_text:
        raise SystemExit("Candidate 0046 QCOM_KGSL is not built-in")
    if "CONFIG_DEBUG_FS=y\n" in cfg_text:
        raise SystemExit("Candidate 0046 unexpectedly enables DEBUG_FS")
    (ROOT/"candidate-0046.config").write_bytes((OUT/".config").read_bytes())

    build_env=env.copy()
    build_env.update({
        "KBUILD_BUILD_USER":"builder",
        "KBUILD_BUILD_HOST":"pangu-build-component-vendor",
        "KBUILD_BUILD_VERSION":"1",
        "KBUILD_BUILD_TIMESTAMP":"Fri Sep 25 15:00:00 UTC 2026",
    })
    sh(["make","-j"+str(os.cpu_count() or 4),"O=out","ARCH=arm64","CC=clang","LLVM=1","LLVM_IAS=1",
        "CROSS_COMPILE=aarch64-linux-gnu-","CROSS_COMPILE_COMPAT=arm-linux-gnueabi-",
        "CLANG_TRIPLE=aarch64-linux-gnu-","Image","modules"], cwd=KERNEL, env=build_env)

    built=OUT/"arch/arm64/boot/Image"
    if not built.is_file() or built.stat().st_size == 0:
        raise SystemExit("Image missing")
    (ROOT/"candidate-0046-Image").write_bytes(built.read_bytes())
    ik=subprocess.check_output([str(KERNEL/"scripts/extract-ikconfig"), str(built)])
    (ROOT/"candidate-0046.ikconfig").write_bytes(ik)
    if TARGET_RELEASE not in built.read_bytes():
        raise SystemExit("target release missing from Candidate 0046 Image")
    ik_text=ik.decode("utf-8", "replace")
    if "CONFIG_QCOM_WATCHDOG_BARK_TIME=20000\n" not in ik_text:
        raise SystemExit("Candidate 0046 embedded bark time is not stock 20000ms")
    if "CONFIG_QCOM_WATCHDOG_PET_TIME=15000\n" not in ik_text:
        raise SystemExit("Candidate 0046 embedded pet time is not stock 15000ms")
    if "CONFIG_QTI_TZ_LOG=y\n" not in ik_text:
        raise SystemExit("Candidate 0046 embedded QTI_TZ_LOG is not enabled")
    if "CONFIG_DEBUG_FS=y\n" in ik_text:
        raise SystemExit("Candidate 0046 embedded DEBUG_FS unexpectedly enabled")
    repack()

    manifest=(
        "candidate=Lisa Candidate 0046 A642L active GPU selector single-variable repair\n"
        f"kernel_source_sha={SOURCE_SHA}\n"
        f"candidate_0018_source_image_sha256={KNOWN_IMAGE_SHA}\n"
        f"candidate_0046_image_sha256={sha256(ROOT/'candidate-0046-Image')}\n"
        f"candidate_0046_boot_sha256={sha256(ROOT/'boot.img')}\n"
        "companion_base=reconstruction/stock/stock-Image-3.09\n"
        "mutation=Candidate0045 baseline + active adreno_gpulist adds existing A642/A642L/A643 selector entries only\n"
        "focus=fix Unknown GPU chip ID 0x06030500 so KGSL creates /dev/kgsl-3d0 and SurfaceFlinger avoids rescueparty crash loop\n"
        "candidate_0018_ikconfig_source=Candidate0040 artifact 11047365059\n"
        "LISA_CANDIDATE_0046_FINAL_GATE=PASS\n"
    )
    (ROOT/"candidate-0046-manifest.txt").write_text(manifest)
    print(manifest)

if __name__ == "__main__":
    main()
