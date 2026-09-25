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
    h.update(b"blob "+str(len(data)).encode()+b"\\0"+data)
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

    (ROOT/"candidate-0021-overlay.txt").write_text(
        f"known_good_repo=LineageOS/android_kernel_xiaomi_sm8350\\n"
        f"known_good_sha={GOOD_SHA}\\n"
        "runtime_oracle=dmesg_TW known-good recovery: QSEE 0x1402000, qnoc 1700000 registered, UFS Gear3/WB, Run /init\\n"
        + "\\n".join(anchor_lines+overlay_lines) + "\\n"
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
    new="\t/* Lisa Candidate 0021 diagnostic: never touch inaccessible IPA QoS MMIO. */\n\t.qosbox = NULL,"
    s=s.replace(old,new,1)

    marker='\tret = clk_bulk_prepare_enable(qp->num_clks, qp->clks);\n'
    if s.count(marker) != 1:
        raise SystemExit(f"unexpected clock-enable marker count: {s.count(marker)}")
    marker_new=marker+'\n\tif (desc == &yupik_aggre2_noc)\n\t\tdev_info(&pdev->dev, "Lisa Candidate 0021: qxm_ipa QoS fully disabled\\n");\n'
    s=s.replace(marker,marker_new,1)
    p.write_text(s)

    out=p.read_text()
    if out.count(".qosbox = NULL,") != 1:
        raise SystemExit("qxm_ipa qosbox disable verification failed")
    if "Lisa Candidate 0021: qxm_ipa QoS fully disabled" not in out:
        raise SystemExit("Candidate 0021 runtime marker missing")

    (ROOT/"candidate-0021-root-cause.txt").write_text(
        "candidate_0019_boot_sha256=ceb2a7a6e4b621cb129f5818f1c6fec245601cd55dfbc756c05e9e888eab4488\n"
        "candidate_0019_exception=synchronous external abort 0x96000010\n"
        "candidate_0019_pc=regmap_mmio_read32le+0x8/0x20\n"
        "candidate_0019_call_path=qcom_icc_set_qos -> qnoc_probe\n"
        "candidate_0019_fault_register_offset=0x10008\n"
        "candidate_0019_aggre2_registration=not reached\n"
        "candidate_0021_control=retain qxm_ipa.qosbox=NULL; overlay known-good 5.4.302 secure/UFS paths\n"
        "companion_base=reconstruction/stock/stock-Image-3.09\n"
    )

def repack():
    PAGE=4096
    stock=bytearray(STOCK_BOOT.read_bytes())
    kernel=(ROOT/"candidate-0021-Image").read_bytes()
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
    (ROOT/"candidate-0021-repack.txt").write_text(
        f"candidate_0021_image_sha256={sha256(kernel)}\n"
        f"candidate_0021_image_bytes={len(kernel)}\n"
        f"stock_kernel_region_bytes={ksz}\n"
        f"kernel_zero_pad_bytes={ksz-len(kernel)}\n"
        f"candidate_0021_boot_sha256={sha256(out)}\n"
        "boot_header_byte_exact=1\n"
        "stock_ramdisk_byte_exact=1\n"
        "changed_bytes_outside_kernel_region=0\n"
        "stock_avb0_metadata_byte_exact=1\n"
        "stock_avbf_footer_byte_exact=1\n"
        "CANDIDATE_0021_FIXED_REGION_REPACK_GATE=PASS\n"
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
    patch_yupik()

    env=os.environ.copy()
    sh(["make","-j"+str(os.cpu_count() or 4),"O=out","ARCH=arm64","CC=clang","LLVM=1","LLVM_IAS=1",
        "CROSS_COMPILE=aarch64-linux-gnu-","CROSS_COMPILE_COMPAT=arm-linux-gnueabi-",
        "CLANG_TRIPLE=aarch64-linux-gnu-","olddefconfig"], cwd=KERNEL, env=env)
    (ROOT/"candidate-0021.config").write_bytes((OUT/".config").read_bytes())

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
    (ROOT/"candidate-0021-Image").write_bytes(built.read_bytes())
    ik=subprocess.check_output([str(KERNEL/"scripts/extract-ikconfig"), str(built)])
    (ROOT/"candidate-0021.ikconfig").write_bytes(ik)
    if TARGET_RELEASE not in built.read_bytes():
        raise SystemExit("target release missing from Candidate 0021 Image")
    repack()

    manifest=(
        "candidate=Lisa Candidate 0021 known-good secure/UFS alignment\n"
        f"kernel_source_sha={SOURCE_SHA}\n"
        f"candidate_0018_source_image_sha256={KNOWN_IMAGE_SHA}\n"
        f"candidate_0021_image_sha256={sha256(ROOT/'candidate-0021-Image')}\n"
        f"candidate_0021_boot_sha256={sha256(ROOT/'boot.img')}\n"
        "companion_base=reconstruction/stock/stock-Image-3.09\n"
        "mutation=retain qxm_ipa QoS hard-disable + align qseecom/qcom_scm/smcinvoke/UFS to known-good 5.4.302\n"
        "fault_register_offset=0x10008\n"
        "LISA_CANDIDATE_0021_FINAL_GATE=PASS\n"
    )
    (ROOT/"candidate-0021-manifest.txt").write_text(manifest)
    print(manifest)

if __name__ == "__main__":
    main()
