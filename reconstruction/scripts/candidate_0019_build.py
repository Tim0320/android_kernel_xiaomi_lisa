#!/usr/bin/env python3
from pathlib import Path
import hashlib
import os
import re
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
KERNEL=ROOT/"kernel"
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

def patch_yupik():
    p=KERNEL/"drivers/interconnect/qcom/yupik.c"
    s=p.read_text()
    m=re.search(r"static struct qcom_icc_qosbox qxm_ipa_qos = \{.*?\.offsets = \{\s*(0x[0-9a-fA-F]+)\s*\},.*?\n\};", s, re.S)
    if not m:
        raise SystemExit("qxm_ipa_qos block not found")
    if int(m.group(1),16) != 0x10000:
        raise SystemExit("unexpected qxm_ipa qos offset")
    old="""        if (qnodes[i]->qosbox) {
            qnodes[i]->noc_ops->set_qos(qnodes[i]);
            qnodes[i]->qosbox->initialized = true;
        }
"""
    # Source uses tabs. Normalize only for exact replacement matching.
    normalized=s.replace("\t","    ")
    if normalized.count(old) != 1:
        raise SystemExit(f"unexpected eager QoS block count: {normalized.count(old)}")
    new="""        if (qnodes[i]->qosbox) {
            /*
             * Lisa Candidate 0019 diagnostic control:
             * defer only qxm_ipa probe-time QoS after the
             * Candidate 0018 external abort at offset 0x10008.
             */
            if (qnodes[i] == &qxm_ipa) {
                dev_info(&pdev->dev, "deferring qxm_ipa QoS initialization\\n");
            } else {
                qnodes[i]->noc_ops->set_qos(qnodes[i]);
                qnodes[i]->qosbox->initialized = true;
            }
        }
"""
    normalized=normalized.replace(old,new,1)
    p.write_text(normalized)
    if "deferring qxm_ipa QoS initialization" not in p.read_text():
        raise SystemExit("patch verification failed")
    (ROOT/"candidate-0019-root-cause.txt").write_text(
        "provider=aggre2_noc@1700000\n"
        "node=qxm_ipa\n"
        "node_id=MASTER_IPA\n"
        "qos_offset=0x10000\n"
        "fault_register_offset=0x10008\n"
        "exception=synchronous external abort 0x96000010\n"
        "control=defer qxm_ipa probe-time QoS only\n"
    )

def repack():
    PAGE=4096
    stock=bytearray(STOCK_BOOT.read_bytes())
    kernel=(ROOT/"candidate-0019-Image").read_bytes()
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
    (ROOT/"candidate-0019-repack.txt").write_text(
        f"candidate_0019_image_sha256={sha256(kernel)}\n"
        f"candidate_0019_image_bytes={len(kernel)}\n"
        f"stock_kernel_region_bytes={ksz}\n"
        f"kernel_zero_pad_bytes={ksz-len(kernel)}\n"
        f"candidate_0019_boot_sha256={sha256(out)}\n"
        "boot_header_byte_exact=1\n"
        "stock_ramdisk_byte_exact=1\n"
        "changed_bytes_outside_kernel_region=0\n"
        "stock_avb0_metadata_byte_exact=1\n"
        "stock_avbf_footer_byte_exact=1\n"
        "CANDIDATE_0019_FIXED_REGION_REPACK_GATE=PASS\n"
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

    patch_yupik()

    env=os.environ.copy()
    sh(["make","-j"+str(os.cpu_count() or 4),"O=out","ARCH=arm64","CC=clang","LLVM=1","LLVM_IAS=1",
        "CROSS_COMPILE=aarch64-linux-gnu-","CROSS_COMPILE_COMPAT=arm-linux-gnueabi-",
        "CLANG_TRIPLE=aarch64-linux-gnu-","olddefconfig"], cwd=KERNEL, env=env)
    (ROOT/"candidate-0019.config").write_bytes((OUT/".config").read_bytes())

    build_env=env.copy()
    build_env.update({
        "KBUILD_BUILD_USER":"builder",
        "KBUILD_BUILD_HOST":"pangu-build-component-vendor",
        "KBUILD_BUILD_VERSION":"1",
        "KBUILD_BUILD_TIMESTAMP":"Tue Sep 22 17:43:28 UTC 2026",
    })
    sh(["make","-j"+str(os.cpu_count() or 4),"O=out","ARCH=arm64","CC=clang","LLVM=1","LLVM_IAS=1",
        "CROSS_COMPILE=aarch64-linux-gnu-","CROSS_COMPILE_COMPAT=arm-linux-gnueabi-",
        "CLANG_TRIPLE=aarch64-linux-gnu-","Image"], cwd=KERNEL, env=build_env)

    built=OUT/"arch/arm64/boot/Image"
    if not built.is_file() or built.stat().st_size == 0:
        raise SystemExit("Image missing")
    (ROOT/"candidate-0019-Image").write_bytes(built.read_bytes())
    ik=subprocess.check_output([str(KERNEL/"scripts/extract-ikconfig"), str(built)])
    (ROOT/"candidate-0019.ikconfig").write_bytes(ik)
    if TARGET_RELEASE not in built.read_bytes():
        raise SystemExit("target release missing from Candidate 0019 Image")
    repack()

    manifest=(
        "candidate=Lisa Candidate 0019 defer IPA QoS probe\n"
        f"kernel_source_sha={SOURCE_SHA}\n"
        f"candidate_0018_source_image_sha256={KNOWN_IMAGE_SHA}\n"
        f"candidate_0019_image_sha256={sha256(ROOT/'candidate-0019-Image')}\n"
        f"candidate_0019_boot_sha256={sha256(ROOT/'boot.img')}\n"
        "companion_base=reconstruction/stock/stock-Image-3.09\n"
        "mutation=defer qxm_ipa probe-time QoS only\n"
        "fault_register_offset=0x10008\n"
        "LISA_CANDIDATE_0019_FINAL_GATE=PASS\n"
    )
    (ROOT/"candidate-0019-manifest.txt").write_text(manifest)
    print(manifest)

if __name__ == "__main__":
    main()
