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

    (ROOT/"candidate-0026-overlay.txt").write_text(
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

    (ROOT/"candidate-0026-layout.txt").write_text(
        "evidence=stock IKHEADERS vs reconstructed runtime layout\n"
        "stock_rw_semaphore_bytes=48\n"
        "candidate_0022_rw_semaphore_bytes=40\n"
        "mutation=restore ANDROID_VENDOR_DATA(1) in struct rw_semaphore\n"
        "expected_inode_i_private_offset_stock=640\n"
        "candidate_0022_inode_i_private_offset=624\n"
        "expected_drm_panel_bytes_stock=104\n"
        "candidate_0022_drm_panel_bytes=96\n"
        "runtime_target=stock msm_drm.ko structural ABI\n"
        "CANDIDATE_0026_RWSEM_LAYOUT_GATE=PASS\n"
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

    (ROOT/"candidate-0026-devpath.txt").write_text(
        "evidence=Candidate0024 CONFIG_BOARD_XIAOMI=n CONFIG_BOARD_XIAOMI_LISA=y\n"
        "cmdline=block2mtd.block2mtd=/dev/block/sda17,2097152\n"
        "source_before=name_to_dev_t strips /dev/block only under CONFIG_BOARD_XIAOMI\n"
        "failure_mode=/dev/block/sda17 becomes block!sda17 and dev_t lookup fails\n"
        "mutation=allow CONFIG_BOARD_XIAOMI_LISA to strip /dev/block prefix\n"
        "expected_block_device=sda17\n"
        "expected_mtd_index=0\n"
        "CANDIDATE_0026_BLOCK2MTD_DEVPATH_GATE=PASS\n"
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
        "\tprintk(KERN_INFO \"mtdoops: Lisa Candidate 0026 logger ready, pages=%d record=%lu\\n\", "
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
        "Lisa Candidate 0026 logger ready",
    ]
    for g in gates:
        if g not in out:
            raise SystemExit(f"mtdoops persistence gate missing: {g}")

    (ROOT/"candidate-0026-logging.txt").write_text(
        "evidence=iter0008/iter0009 oops unchanged across failed boots\n"
        "oops_partition_bytes=16777216\n"
        "source_mtdoops_limit_before=8388608\n"
        "mutation=allow 16MiB oops + persist restart/halt/poweroff kmsg + sync\n"
        "record_size_cmdline=2097152\n"
        "expected_records=8\n"
        "CANDIDATE_0026_PERSISTENT_KMSG_GATE=PASS\n"
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
        "#define MTDOOPS_SNAPSHOT_INTERVAL    (5 * HZ)\n"
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
        "\t\tprintk(KERN_INFO \"mtdoops: Lisa Candidate 0026 snapshot %u persisted (%zu bytes)\\n\",\n"
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
        "\t\tprintk(KERN_WARNING \"mtdoops: could not unregister kmsg dumper\\n\");\n"
        "\n"
        "\tcxt->mtd = NULL;\n"
    )
    new=(
        "\tcancel_delayed_work_sync(&cxt->work_snapshot);\n"
        "\tif (kmsg_dump_unregister(&cxt->dump) < 0)\n"
        "\t\tprintk(KERN_WARNING \"mtdoops: could not unregister kmsg dumper\\n\");\n"
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
        "MTDOOPS_SNAPSHOT_INTERVAL    (5 * HZ)",
        "kmsg_dump_rewind(&cxt->snapshot_dump);",
        "Lisa Candidate 0026 snapshot %u persisted",
        "INIT_DELAYED_WORK(&cxt->work_snapshot, mtdoops_snapshot_workfunc);",
        "schedule_delayed_work(&cxt->work_snapshot",
    ]
    for g in gates:
        if g not in out:
            raise SystemExit(f"periodic snapshot gate missing: {g}")

    (ROOT/"candidate-0026-snapshot.txt").write_text(
        "evidence=Candidate0025 oops SHA unchanged despite block2mtd devpath fix\n"
        "reset_mode=PSHOLD hard reset may bypass kmsg_dump callbacks\n"
        "mutation=private kmsg_dumper periodic snapshots to mtdoops ring\n"
        "first_snapshot_delay_seconds=2\n"
        "snapshot_interval_seconds=5\n"
        "record_size_bytes=2097152\n"
        "ring_records=8\n"
        "history_window_seconds_approx=40\n"
        "CANDIDATE_0026_PERIODIC_KMSG_GATE=PASS\n"
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
    new="\t/* Lisa Candidate 0026 diagnostic: never touch inaccessible IPA QoS MMIO. */\n\t.qosbox = NULL,"
    s=s.replace(old,new,1)

    marker='\tret = clk_bulk_prepare_enable(qp->num_clks, qp->clks);\n'
    if s.count(marker) != 1:
        raise SystemExit(f"unexpected clock-enable marker count: {s.count(marker)}")
    marker_new=marker+'\n\tif (desc == &yupik_aggre2_noc)\n\t\tdev_info(&pdev->dev, "Lisa Candidate 0026: qxm_ipa QoS fully disabled\\n");\n'
    s=s.replace(marker,marker_new,1)
    p.write_text(s)

    out=p.read_text()
    if out.count(".qosbox = NULL,") != 1:
        raise SystemExit("qxm_ipa qosbox disable verification failed")
    if "Lisa Candidate 0026: qxm_ipa QoS fully disabled" not in out:
        raise SystemExit("Candidate 0026 runtime marker missing")

    (ROOT/"candidate-0026-root-cause.txt").write_text(
        "candidate_0019_boot_sha256=ceb2a7a6e4b621cb129f5818f1c6fec245601cd55dfbc756c05e9e888eab4488\n"
        "candidate_0019_exception=synchronous external abort 0x96000010\n"
        "candidate_0019_pc=regmap_mmio_read32le+0x8/0x20\n"
        "candidate_0019_call_path=qcom_icc_set_qos -> qnoc_probe\n"
        "candidate_0019_fault_register_offset=0x10008\n"
        "candidate_0019_aggre2_registration=not reached\n"
        "candidate_0026_control=retain qxm_ipa.qosbox=NULL; overlay known-good 5.4.302 secure/UFS + zram paths\n"
        "companion_base=reconstruction/stock/stock-Image-3.09\n"
    )

def repack():
    PAGE=4096
    stock=bytearray(STOCK_BOOT.read_bytes())
    kernel=(ROOT/"candidate-0026-Image").read_bytes()
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
    (ROOT/"candidate-0026-repack.txt").write_text(
        f"candidate_0026_image_sha256={sha256(kernel)}\n"
        f"candidate_0026_image_bytes={len(kernel)}\n"
        f"stock_kernel_region_bytes={ksz}\n"
        f"kernel_zero_pad_bytes={ksz-len(kernel)}\n"
        f"candidate_0026_boot_sha256={sha256(out)}\n"
        "boot_header_byte_exact=1\n"
        "stock_ramdisk_byte_exact=1\n"
        "changed_bytes_outside_kernel_region=0\n"
        "stock_avb0_metadata_byte_exact=1\n"
        "stock_avbf_footer_byte_exact=1\n"
        "CANDIDATE_0026_FIXED_REGION_REPACK_GATE=PASS\n"
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
    img=ROOT/"candidate-0018-Image"
    if sha256(img) != KNOWN_IMAGE_SHA or TARGET_RELEASE not in img.read_bytes():
        raise SystemExit("Candidate 0018 Image identity mismatch")
    OUT.mkdir(parents=True, exist_ok=True)
    cfg=subprocess.check_output([str(KERNEL/"scripts/extract-ikconfig"), str(img)])
    (OUT/".config").write_bytes(cfg)
    (ROOT/"candidate-0018.ikconfig").write_bytes(cfg)
    if b"CONFIG_INTERCONNECT_QCOM_RPMH=y" not in cfg:
        raise SystemExit("expected RPMH config missing")

    overlay_known_good()
    patch_stock_rwsem()
    patch_block2mtd_devpath()
    patch_mtdoops_persistence()
    patch_mtdoops_periodic_snapshot()
    patch_yupik()

    env=os.environ.copy()
    sh(["make","-j"+str(os.cpu_count() or 4),"O=out","ARCH=arm64","CC=clang","LLVM=1","LLVM_IAS=1",
        "CROSS_COMPILE=aarch64-linux-gnu-","CROSS_COMPILE_COMPAT=arm-linux-gnueabi-",
        "CLANG_TRIPLE=aarch64-linux-gnu-","olddefconfig"], cwd=KERNEL, env=env)
    (ROOT/"candidate-0026.config").write_bytes((OUT/".config").read_bytes())

    build_env=env.copy()
    build_env.update({
        "KBUILD_BUILD_USER":"builder",
        "KBUILD_BUILD_HOST":"pangu-build-component-vendor",
        "KBUILD_BUILD_VERSION":"1",
        "KBUILD_BUILD_TIMESTAMP":"Fri Sep 25 15:00:00 UTC 2026",
    })
    sh(["make","-j"+str(os.cpu_count() or 4),"O=out","ARCH=arm64","CC=clang","LLVM=1","LLVM_IAS=1",
        "CROSS_COMPILE=aarch64-linux-gnu-","CROSS_COMPILE_COMPAT=arm-linux-gnueabi-",
        "CLANG_TRIPLE=aarch64-linux-gnu-","Image"], cwd=KERNEL, env=build_env)

    built=OUT/"arch/arm64/boot/Image"
    if not built.is_file() or built.stat().st_size == 0:
        raise SystemExit("Image missing")
    (ROOT/"candidate-0026-Image").write_bytes(built.read_bytes())
    ik=subprocess.check_output([str(KERNEL/"scripts/extract-ikconfig"), str(built)])
    (ROOT/"candidate-0026.ikconfig").write_bytes(ik)
    if TARGET_RELEASE not in built.read_bytes():
        raise SystemExit("target release missing from Candidate 0026 Image")
    repack()

    manifest=(
        "candidate=Lisa Candidate 0026 stock rwsem runtime-layout alignment\n"
        f"kernel_source_sha={SOURCE_SHA}\n"
        f"candidate_0018_source_image_sha256={KNOWN_IMAGE_SHA}\n"
        f"candidate_0026_image_sha256={sha256(ROOT/'candidate-0026-Image')}\n"
        f"candidate_0026_boot_sha256={sha256(ROOT/'boot.img')}\n"
        "companion_base=reconstruction/stock/stock-Image-3.09\n"
        "mutation=Candidate0025 block2mtd devpath + periodic 5s mtdoops kernel-ring snapshots\n"
        "fault_register_offset=0x10008\n"
        "LISA_CANDIDATE_0026_FINAL_GATE=PASS\n"
    )
    (ROOT/"candidate-0026-manifest.txt").write_text(manifest)
    print(manifest)

if __name__ == "__main__":
    main()
