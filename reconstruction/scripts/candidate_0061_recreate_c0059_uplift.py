#!/usr/bin/env python3
from pathlib import Path
from types import SimpleNamespace
import argparse, os, sys

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
    proc50.apply(root,kernel)
    ownership.retained=lambda _root: SimpleNamespace(apply=lambda _r,_k: None)
    ownership.apply(root,kernel)
    perf.apply_sources(root,kernel)
    bpf.apply(root,kernel)
    print("C0059_INHERITED_SOURCE_STACK_RECREATED=PASS")

if __name__=="__main__":
    main()
