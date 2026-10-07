#!/usr/bin/env python3
from pathlib import Path
from types import SimpleNamespace
import argparse, ast, hashlib, os, sys

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--package",type=Path,required=True)
    ap.add_argument("--kernel",type=Path,required=True)
    a=ap.parse_args()
    root=a.package.resolve(); kernel=a.kernel.resolve()
    sys.path.insert(0,str(root/"reconstruction/scripts"))

    import candidate_0046_build as c46
    import candidate_0050_proc_abi_patch as proc50
    import candidate_0056_power_patch as power
    import candidate_0059_ownership_patch as ownership
    import candidate_0059_perf_port as perf
    import candidate_0059_bpf_port as bpf

    ufs=(kernel/"drivers/scsi/ufs/ufshcd.c").read_text()
    mem=(kernel/"drivers/misc/mi-memory/mem_interface.c").read_text()
    if "set_ufs_hba_data(sdev);" not in ufs or "void set_ufs_hba_data(" not in mem:
        raise RuntimeError("Frozen 5.4.289 source no longer carries expected Candidate0055 UFS bridge")

    power.retained=lambda _root: SimpleNamespace(apply=lambda _r,_k: None)
    if not (kernel/"kernel/power/lisa_power_compat.c").exists():
        power.apply(root,kernel)

    c46.ROOT=root; c46.KERNEL=kernel; c46.OUT=kernel/"out"
    c46.patch_qgki_module_abi()

    # Candidate0059 was built through the 0054 -> 0053 -> 0046 lineage.  The
    # frozen source checkout predates those recipe-time IPA/PAS mutations, so
    # recreating C0059 must replay the verified Lisa/Yupik runtime contract as
    # well as the ABI/performance overlays.  Keep the historical builders
    # pinned and invoke only the bounded prerequisites plus the two C0053 IPA
    # endpoint adaptations; do not execute a historical build or copy donor
    # sources wholesale.
    c46.patch_block2mtd_devpath()
    c46.patch_mtdoops_persistence()
    c46.patch_mtdoops_periodic_snapshot()
    c46.patch_mtdoops_fast_snapshot_io()
    c46.patch_ipa_pil_stage_trace()
    c46.patch_ipa_pas_sync_checkpoint()

    # candidate_0053_build.py is a historical executable builder, not an
    # import-safe library: its module tail immediately starts the old C0053
    # camera/kernel build.  Pin its Git blob and execute only the two reviewed
    # IPA/PAS function definitions through AST extraction.
    c53_path = root/"reconstruction/scripts/candidate_0053_build.py"
    c53_bytes = c53_path.read_bytes()
    c53_blob = hashlib.sha1(
        b"blob " + str(len(c53_bytes)).encode() + b"\0" + c53_bytes
    ).hexdigest()
    c53_expected_blob = "d3111485e075156687c5eee50546ba42417dd2fa"
    if c53_blob != c53_expected_blob:
        raise RuntimeError(
            "Candidate0053 recipe blob changed; review before C0061 replay: "
            + c53_blob
        )

    c53_tree = ast.parse(c53_bytes.decode("utf-8"), filename=str(c53_path))
    c53_wanted = {
        "patch_ipa_pas_metadata_dma_retention",
        "candidate0053_patch_ipa_pas_shmbridge",
    }
    c53_nodes = [
        node for node in c53_tree.body
        if isinstance(node, ast.FunctionDef) and node.name in c53_wanted
    ]
    if {node.name for node in c53_nodes} != c53_wanted:
        raise RuntimeError("Pinned Candidate0053 IPA/PAS functions missing")
    c53_module = ast.Module(body=c53_nodes, type_ignores=[])
    ast.fix_missing_locations(c53_module)
    c53_ns = {
        "__builtins__": __builtins__,
        "ROOT": root,
        "KERNEL": kernel,
        "_candidate0053_patch_ipa_pas_shmbridge_base": c46.patch_ipa_pas_shmbridge,
    }
    exec(compile(c53_module, str(c53_path), "exec"), c53_ns, c53_ns)
    c53_ns["candidate0053_patch_ipa_pas_shmbridge"]()
    c53_ns["patch_ipa_pas_metadata_dma_retention"]()

    ipa_tz=(kernel/"drivers/soc/qcom/subsys-pil-tz.c").read_text()
    scm=(kernel/"drivers/firmware/qcom_scm.c").read_text()
    mtd=(kernel/"drivers/mtd/mtdoops.c").read_text()
    mounts=(kernel/"init/do_mounts.c").read_text()
    yupik=(kernel/"arch/arm64/boot/dts/vendor/qcom/yupik.dtsi").read_text()
    ipa_gates = (
        ("block2mtd Lisa devpath", "defined(CONFIG_BOARD_XIAOMI_LISA)" in mounts),
        ("synchronous mtdoops checkpoint", "void lisa_mtdoops_checkpoint(const char *tag)" in mtd),
        ("PAS pre-auth checkpoint", 'lisa_mtdoops_checkpoint("ipa_before_pas_auth_reset");' in ipa_tz),
        ("firmware SHMBridge", "qtee_shmbridge_register(d->lisa_ipa_fw_addr" in ipa_tz),
        ("C0053 full-region endpoint", "LISA0053_IPA_REGION stage=mem_setup_full" in ipa_tz),
        ("PAS15 metadata retention", "LISA0053_IPA_METADATA stage=after_auth_reset" in scm),
        ("Yupik IPA reserved region", "reg = <0x0 0x8b710000 0x0 0xa000>;" in yupik),
        ("Yupik IPA firmware identity", 'qcom,firmware-name = "yupik_ipa_fws";' in yupik),
    )
    missing = [name for name, ok in ipa_gates if not ok]
    if missing:
        raise RuntimeError("Candidate0059 IPA/PAS inheritance gate missing: " + ", ".join(missing))
    print("C0061_C0059_IPA_PAS_INHERITANCE=PASS")
    proc50.apply(root,kernel)
    ownership.retained=lambda _root: SimpleNamespace(apply=lambda _r,_k: None)
    ownership.apply(root,kernel)
    perf.apply_sources(root,kernel)
    bpf.apply(root,kernel)

    # Frozen Candidate0059 commit 6e568a... intentionally remains immutable, but
    # it contains two tracked legacy patch-reject sidecars from the old FTS
    # driver import. They are not kernel source and are unrelated to the
    # 5.4.289->5.4.302 stable delta. C0061 removes only these verified inherited
    # artifacts so the Direct-302 no-.rej gate reflects newly-created rejects.
    legacy_rejects = (
        "drivers/input/touchscreen/fts_dual/secondary/fts_lib/Makefile.rej",
        "drivers/input/touchscreen/fts_spi/fts_lib/Makefile.rej",
    )
    for rel in legacy_rejects:
        p = kernel / rel
        if not p.is_file():
            raise RuntimeError("Expected frozen Candidate0059 legacy reject missing: " + rel)
        data = p.read_text(errors="replace")
        if (
            "--- drivers/input/touchscreen/fts_521/fts_lib/Makefile" not in data
            or "CONFIG_TOUCHSCREEN_ST_FTS_V521" not in data
        ):
            raise RuntimeError("Refusing to remove unexpected reject content: " + rel)
        p.unlink()

    leftovers = sorted(str(p.relative_to(kernel)) for p in kernel.rglob("*.rej"))
    if leftovers:
        raise RuntimeError(
            "Unexpected reject sidecars remain after frozen C0059 hygiene cleanup: "
            + ", ".join(leftovers)
        )
    print("C0061_C0059_LEGACY_REJECT_CLEANUP=PASS count=2")
    print("C0059_INHERITED_SOURCE_STACK_RECREATED=PASS")

if __name__=="__main__":
    main()
